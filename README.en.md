# Peha PHC for Home Assistant

[Nederlandse versie](README.md)

Home Assistant integration for the Peha PHC bus. Control relays, roller shutters and virtual buttons from Home Assistant, and see the inputs and the bus traffic.

> **Test version 0.1.1.** This integration is new and looking for testers with a real Peha PHC installation. Please read the warning below first.

## Warning

This integration controls real relays and roller shutters. It is not a safety system. Make sure your installation can always be operated manually, and use the integration at your own risk.

## What can the integration do?

- **Relay module (AMD):** 8 switches, each channel on or off.
- **Roller shutter module (JRM):** 4 covers with open, close and stop, and a run time per channel.
- **Input module (IMD):** 16 binary sensors, and an event for every input action.
- **Virtual buttons:** a click on an input, with the functions from the Node-RED flow.
- **Port switches:** the USB cable and the bus dongle can be closed independently, for example to use Node-RED again.
- **Log sensors:** all sent packets and all processed bus packets.

## Requirements

- Home Assistant, a recent version. The minimum version has not been determined yet.
- A Peha PHC installation with an STM control unit, connected with a USB cable.
- An RS485 bus dongle with USB, connected to the Peha bus.
- Both USB devices on the same Home Assistant host. Home Assistant needs access to the ports. On Linux this is usually the `dialout` group.
- Node-RED must not use the ports at the same time.

## Wiring

![Peha PHC wiring](https://i.imgur.com/602oKcF.png)

- The USB cable goes to the STM control unit. By default this is `/dev/ttyACM0`. Commands are sent here, with C0/C1 framing.
- The RS485 bus dongle goes to the Peha bus. By default this is `/dev/ttyUSB0`. Raw bus data comes from here.
- Both ports use 19200 baud, 8 data bits, no parity and 2 stop bits.
- Preferably use the stable names under `/dev/serial/by-id/`. The names `ttyACM0` and `ttyUSB0` can swap order after a restart.

The wiring of the bus and the control unit is shown in the photo above.

## Installation

1. Copy the folder `custom_components/peha_phc` to the `custom_components` folder of Home Assistant. You can also add this repository in HACS as a custom repository of type integration.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and choose **Peha PHC**.
4. Enter the ports. The defaults are `/dev/ttyACM0` for the USB cable and `/dev/ttyUSB0` for the bus dongle. If the connection fails, you get a message. Then check the path and whether Node-RED uses the port.

Already running version 0.1.0 or newer? Then only replace the folder and restart Home Assistant. Existing entities keep their id.

## Adding modules

Go to **Devices & services → Peha PHC → Configure**. For each module you only enter the PHC number and a name.

| Module | Count | Bus address |
|---|---|---|
| Input (IMD) | 16 inputs | `0x00` + PHC number |
| Relay (AMD) | 8 channels | `0x40` + PHC number |
| Roller shutter (JRM) | 4 channels | `0x40` + PHC number |

The PHC number is the number you set on the module, from 0 to 31. Relays and roller shutters share the address range `0x40` to `0x5F`, so one number can only be one output module. The integration checks this when you add a module.

You add a virtual button in the same way. Choose the PHC number of the input module, the channel (0 to 15), the function and a name.

## Entities

Entity names are in Dutch, as they appear in Home Assistant.

**Hub (Peha PHC)**

- *Poort USB-kabel (STM)* and *Poort busdongle (RS485)*: switches, on by default. Off closes the port for real, and the state is kept after a restart.
- *Verstuurde pakketten (USB-kabel)*: sensor with the C0 ... C1 packets sent to the STM.
- *Verwerkte bus-pakketten*: sensor with the lines the parser has processed.

The two log sensors have an attribute `pakketten` (a list, as JSON) and an attribute `tekst` (the same lines as plain text).

**Relay module**

- *Kanaal 0* through *Kanaal 7*: switches.
- *Status*: sensor with eight characters. The position shows the channel, for example `00000000`.
- *Status opvragen* (request status): button.
- *Laatste bus-data* (last bus data): diagnostic sensor.

**Roller shutter module**

- *Kanaal 0* through *Kanaal 3*: covers, with the attribute `status`.
- *Looptijd kanaal 0* through *3* (run time): sliders from 3 to 180 seconds. Default 20, 25, 30 and 16 seconds.
- *Kanaal N status*: sensor showing open, closed, halted, opening, closing or unknown.
- *Kanaal N omhoog* (up) and *Kanaal N omlaag* (down): buttons that always send a command.
- *Status*, *Status opvragen* and *Laatste bus-data*.

**Input module**

- *Ingang 0* through *Ingang 15* (input): binary sensors.
- *Status*: sensor in the form `inputs,LEDs`, two times 16 characters.
- *Status opvragen* and *Laatste bus-data*.

**Virtual button**

- One button per virtual input. One click sends one command.

## Virtual functions

| Function | Meaning | Code |
|---|---|---|
| `kort` | On > 0 seconds | `0x02` |
| `uit_lt_1` | Off < 1 second | `0x03` |
| `lang` | On > 1 second | `0x04` |
| `uit_gt_1` | Off > 1 second | `0x05` |
| `extra_lang` | On > 2 seconds | `0x06` |

## Roller shutters

- A command always goes to the module, also during a movement.
- At rest the cover is `unknown`, so the buttons stay enabled. During a movement it is `opening` or `closing`.
- The actual status is in the attribute `status` and in the sensor *Kanaal N status*.
- A stop during a movement gives `halted`. Home Assistant has no such state for covers.
- If no end message arrives, a fallback closes the movement after the run time plus 5 seconds.
- After a restart, the integration restores the last known status from the sensor.

## Events and services

When an input action happens, the integration fires the event `peha_phc_ingang`. It contains the fields `module`, `adres`, `naam`, `kanaal` and `actie`. The action is `kort_ingedrukt`, `kort_losgelaten`, `lang_ingedrukt`, `lang_losgelaten`, `extra_lang_ingedrukt` or `losgelaten`.

There are two services:

- `peha_phc.stuur_commando` sends a raw command, with the fields `adres` and `data` in hex. Useful for testing.
- `peha_phc.virtuele_ingang` sends a virtual function, with the fields `adres` (the PHC number), `kanaal` and `functie`.

## Logs and troubleshooting

For more detail, add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.peha_phc: debug
```

Common messages:

- **Port not available:** check the path, the permissions, and whether Node-RED uses the port.
- **Module unavailable:** one of the ports is off or not connected.
- **Bus address not configured:** traffic arrives from a PHC number you have not added yet.

## Known limitations and assumptions

- Roller shutters: I read the timer events as the end of the movement in the last chosen direction. This still needs to be confirmed on real hardware.
- A virtual button sends one command, without a release and without a wait time.
- Not all PHC versions and module versions have been tested. Tell us if your installation differs.

## Testing and feedback

We are looking for testers with a Peha PHC installation. These are the things I would like to see tested:

- relays on and off, and the status sensor
- roller shutters up, down and stop, and the sensor *Kanaal N status*
- inputs: a button press gives an event, and the status is correct after the automatic status request
- virtual buttons
- a restart of Home Assistant: do the port switches and the roller shutter status stay correct?

Report problems via [GitHub Issues](https://github.com/v12345vtm/PEHACustomComponent_HA/issues). Include the version of the integration and of Home Assistant, your module list, and the text of the two log sensors.

## Development

Run the protocol and state tests without Home Assistant:

```bash
python3 -m unittest discover -s tests -v
```

Changes per version are in [CHANGELOG.md](CHANGELOG.md). The integration is based on the Node-RED flow for the PHC bus.
