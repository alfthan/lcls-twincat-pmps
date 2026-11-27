#!/usr/bin/env python3
"""Rewrite the Declaration CDATA of FB_TempSensor_FFO.TcPOU with comments only.

Comment-only edit: the declaration token stream (identifiers, types, defaults,
pragmas) is preserved exactly; only (* *) and // comments are added.
"""
import re
import sys

PATH = "lcls-twincat-pmps/PMPS/AncillaryComponents/FB_TempSensor_FFO.TcPOU"

HEADER = """(*
    FB_TempSensor_FFO - trip a PMPS fast fault when a temperature sensor is too
    hot or has lost its connection.

    Purpose:
        Add beam-off protection to FB_TempSensor (LCLSGeneral). The base block turns
        the raw ADC counts of the sensor into fTemp in degrees Celsius and reports
        bConnected; this block compares fTemp against a configurable trip point and
        drives one FB_FastFault registration, so an over-temperature reading or a
        lost sensor connection drops the shared fast-fault output (FFO) - and with it
        the beam - at fast-fault latency instead of waiting for a slower sequence to
        notice the same condition.

    Usage:
        Declare one instance per temperature sensor, call it every cycle from the task
        that owns the sensor, and wire the trip point and the FFO:

            fbTempSensor_FFO(
                fFaultThreshold := <trip point, deg C>,
                fHysteresis     := <release band, %>,
                sDevName        := <device name for the fast-fault diagnostics>,
                bVeto           := <TRUE while the device is out of the beam>,
                bAutoReset      := <TRUE for a self-clearing fault>,
                io_fbFFHWO      := <the station's FB_HardwareFFOutput>);

        fResolution, iRaw, bError, bUnderrange and bOverrange come from the base
        block; the four boolean/raw inputs are terminal-linked by the project and
        fTemp/bConnected are the base block's published results. io_fbFFHWO must be
        bound to a real FFO instance: the block registers one fast fault in that
        FFO's pool on its first scan, and nothing ever deregisters it. When the pool
        is full the registration fails, the FFO logs it and holds the beam off
        (xFastFaultRegFail), so the FFO must be sized (PMPS_PARAM.MAX_FAST_FAULTS)
        for every contributor.

    Objectives:
        - One block owns the temperature trip point, so every temperature sensor in a
          station contributes to the beam permit the same way and is configured in one
          place instead of inside each sequence.
        - Trip on the reached threshold and release only after the reading has fallen
          clearly below it: fHysteresis is a percentage of the trip point (the body
          clamps it to 1..100), so the release band scales with the setpoint and a bad
          value cannot make it zero-wide (chattering) or a full 100 % (never releasing).
        - Fail safe on the sensor itself: bConnected is FALSE when the ADC reports both
          bOverrange and bError, and that unconditionally clears bFAULT_OK, so a
          disconnected, broken or unpowered sensor cannot leave the beam permitted even
          while its last reading happened to be cool.
        - Let a device that is out of the beam be masked with bVeto instead of being
          bypassed elsewhere, and let the fault clear itself (bAutoReset) once the
          condition goes away, without an operator reset.
        - Report every change of state once, through the shared MPS logger.

    History:
        2022-05-13  ghalym               Created (d3566dc): trip threshold, hysteresis
                                         and veto option, so a device removed from the
                                         beam does not have to be bypassed.
        2022-05-16  ghalym               Fixed the pytmc pragma syntax and the bVeto
                                         comment; added the bAutoReset input (980a103).
        2022-11-05  ghalym               Re-added under AncillaryComponents with the
                                         JSON reader / beam-parameter restructuring
                                         (4ad2c5b).
        2024-01-29  ghalym               Reformatted by pre-commit (1335761).
        2026-09-16  Yann Stephen Mandza  Removed the XAE product version from the
                                         project files (f77073f).
        2026-11-27  Scirix agent         Documentation only: added this header and the
                                         per-declaration meaning/units comments; no
                                         functional change (audit finding #231, task
                                         #333, convention conv_321640e095c0).

    Note:
        The fast-fault description is the string literal on the FFO instance below. It
        keeps its original wording ("temprature", and no mention of the shared
        sensor-disconnect trip) because it is published to the fast-fault diagnostics
        (FB_HardwareFFOutput.astFF[].Info.Desc); that wording is deliberately not
        changed by this documentation-only edit.
*)
"""

DECL = """FUNCTION_BLOCK FB_TempSensor_FFO EXTENDS FB_TempSensor
VAR_INPUT
    (* Trip point. The fault is raised when the scaled temperature fTemp (deg C,
    published by the base block) reaches this value, and released only once fTemp
    drops below fFaultThreshold - fFaultThreshold * fHysteresis / 100. Value and
    units are those of the FAULT_SP PV (deg C, 2 decimals); a value at or below the
    ambient reading therefore keeps the fault asserted continuously. *)
    {attribute 'pytmc' := '
        pv: FAULT_SP
        io: input
        field: EGU C
        field: PREC 2
    '}
    fFaultThreshold : LREAL;
    (* Hysteresis, in percent of fFaultThreshold (FAULT_SP_HYS PV, EGU %, default
    1 %). Defines the band below the trip point over which the fault stays raised,
    so a reading hovering at the setpoint does not make the fast fault chatter.
    Clamped to 1..100 in the body: below 1 % there is effectively no band, and at
    100 % the release point would be 0 deg C, i.e. the fault would never clear. *)
    {attribute 'pytmc' := '
        pv: FAULT_SP_HYS
        io: input
        field: EGU %
        field: PREC 2
    '}
    fHysteresis : LREAL :=1;
    (* Logical device name of this sensor, reported to the fast-fault output as
    FB_FastFault.i_DevName and published in the FF diagnostics info string. Free
    text with no default, so a forgotten assignment leaves the fault anonymous;
    use the same name this device carries elsewhere in the project. *)
    sDevName: STRING;
    (* Veto: TRUE masks this block's whole contribution to the FFO, i.e. both the
    over-temperature trip and the sensor-disconnect trip, so the beam stays
    permitted while the device is deliberately out of the service (e.g. removed
    from the beam). Defaults to FALSE so a forgotten assignment faults rather than
    permits. *)
    bVeto : BOOL:=FALSE;
    (* Auto reset: forwarded to FB_FastFault.i_xAutoReset. TRUE (default here, while
    FB_FastFault itself defaults to FALSE) makes the fault non-latching: it clears
    by itself once fTemp is back inside the release band and the sensor is
    connected again. FALSE latches it until the block is re-initialised - this
    block leaves FFO.i_xReset unconnected, so there is no operator reset path. *)
    bAutoReset : BOOL:=TRUE;
END_VAR
VAR_IN_OUT
    (* The station's fast-fault output. One fast fault (type code 16#f700) is
    registered into this instance on the first scan; the reference must be bound
    by the caller, the block does not validate it. *)
    io_fbFFHWO    :    FB_HardwareFFOutput;
END_VAR
VAR_OUTPUT
END_VAR
VAR
    {attribute 'instance-path'}
    {attribute 'noinit'}
    (* Instance path filled in by TwinCAT (noinit: not zeroed on download) so the
    FB can be identified in TwinCAT diagnostics. Kept for consistency with the
    other PMPS blocks; this block's own logic never reads it - the path published
    in the FF diagnostics is the FFO's own sPath. *)
    sPath: STRING;
    (* Per-scan no-fault condition, TRUE = beam may stay on. Latched FALSE when the
    temperature reaches fFaultThreshold and forced FALSE while the sensor is
    disconnected (the R= below the trip evaluation), which is also the safe
    default, so a sensor that is dead from the first scan never permits beam. *)
    bFAULT_OK:BOOL :=FALSE;
    (* The single fast fault this block contributes: i_xOK follows bFAULT_OK OR
    bVeto, and i_xReset is left unconnected. Description and type code are fixed at
    declaration (16#f700 is the PMPS type code shared with FB_PressSensor_FFO) and
    are published to the FF diagnostics on registration. *)
    FFO    :    FB_FastFault :=(
        i_Desc := 'Fault occurs when the temprature trip point is reached',
        i_TypeCode := 16#f700);
    (* Edge detector used by ACT_Logger. Named "reset" but clocked on FFO.i_xOK, so
    it fires on the rising edge, i.e. when the fault has cleared and the beam is
    permitted again; that edge produces the "condition clear" log message. *)
    rtRESET\t:\tR_TRIG;
    (* Edge detector used by ACT_Logger: fires on the falling edge of FFO.i_xOK,
    i.e. when the fault is raised, and produces the "Temp Threshold Fault" message. *)
    ftFAULT\t:\tF_TRIG;
    (* Edge detector used by ACT_Logger: fires on the falling edge of bConnected,
    i.e. when the sensor is lost, and produces the "Sensor Connection Fault"
    message. *)
    ftConnected\t:\tF_TRIG;
    (* Shared diagnostics logger, MPS subsystem. nMinTimeViolationAcceptable := 10 is
    the logger's circuit-breaker tolerance: up to 10 messages may violate the
    minimum interval between calls before the logger trips and suppresses output. *)
    fbLogger : FB_LogMessage := (eSubsystem:=E_SubSystem.MPS, nMinTimeViolationAcceptable:=10);
END_VAR
"""

ACTION_HEADER = """(* ACT_Logger
   Edge-triggered diagnostics for this block, called from the body every cycle.
   Emits one message per transition through fbLogger (subsystem MPS): Critical when
   the temperature fault is raised (falling FFO.i_xOK) and when the sensor is lost
   (falling bConnected), Info when the fault clears (rising FFO.i_xOK). Nothing is
   logged while the state is steady. *)
"""

# A block comment in IEC 61131-3 ST does not nest, so a "*)" inside a comment body
# would terminate it early. Every "(*" must therefore pair with exactly one "*)".
for _name, _chunk in (("header", HEADER), ("decl", DECL), ("action", ACTION_HEADER)):
    if _chunk.count("(*") != _chunk.count("*)"):
        print(
            "internal error: unbalanced comment delimiters in %s (%d vs %d)"
            % (_name, _chunk.count("(*"), _chunk.count("*)")),
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> int:
    with open(PATH, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8-sig")
    assert text.count("\r\n") == text.count("\n"), "expected pure CRLF"

    m = re.search(r"<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>", text, re.S)
    if not m:
        print("declaration CDATA not found", file=sys.stderr)
        return 1
    old_decl = m.group(1)
    if not old_decl.startswith("FUNCTION_BLOCK FB_TempSensor_FFO EXTENDS FB_TempSensor\r\n"):
        print("unexpected declaration start", file=sys.stderr)
        return 1

    new_decl = (HEADER + DECL).replace("\n", "\r\n").replace("\\t", "\t")
    text = text[: m.start(1)] + new_decl + text[m.end(1) :]

    marker = (
        '<Action Name="ACT_Logger" Id="{2576dc82-55ff-4de9-a3d9-4a950f0ab28a}">\r\n'
        "      <Implementation>\r\n        <ST><![CDATA["
    )
    if text.count(marker) != 1:
        print("ACT_Logger marker not unique/found", file=sys.stderr)
        return 1
    text = text.replace(marker, marker + ACTION_HEADER.replace("\n", "\r\n"))

    with open(PATH, "wb") as f:
        f.write(("\ufeff" + text).encode("utf-8"))
    print("written", PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
