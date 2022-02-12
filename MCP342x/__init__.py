"""Access Microchip MCP342x analogue to digital converters."""

import logging
import time


__author__ = 'Steve Marple'
__version__ = '0.3.5'
__license__ = 'MIT'


class MCP342x(object):
    """
    Class to represent MCP342x ADC.
    """
    _gain_mask            = 0b00000011
    _resolution_mask      = 0b00001100
    _continuous_mode_mask = 0b00010000
    _channel_mask         = 0b01100000
    _not_ready_mask       = 0b10000000

    _gain_to_config = {1: 0b00,
                       2: 0b01,
                       4: 0b10,
                       8: 0b11}
    _resolution_to_config = {12: 0b0000,
                             14: 0b0100,
                             16: 0b1000,
                             18: 0b1100}
    _channel_to_config = {0: 0b0000000, 
                          1: 0b0100000, 
                          2: 0b1000000, 
                          3: 0b1100000}

    _conversion_time = {12: 1.0/240,
                        14: 1.0/60,
                        16: 1.0/15,
                        18: 1.0/3.75}

    _resolution_to_lsb = {12: 1e-3,
                          14: 250e-6,
                          16: 62.5e-6,
                          18: 15.625e-6}

    @staticmethod
    def general_call_reset(bus):
        bus.write_byte(0, 6)
        return

    @staticmethod
    def general_call_latch(bus):
        bus.write_byte(0, 4)
        return

    @staticmethod
    def general_call_convert(bus):
        logger.debug('general_call_convert')
        bus.write_byte(0, 8)
        return

    @staticmethod
    def config_to_gain(config):
        return [g for g, c in iter(MCP342x._gain_to_config.items()) if c == config & MCP342x._gain_mask][0]

    @staticmethod
    def config_to_resolution(config):
        return [g for g, c in iter(MCP342x._resolution_to_config.items()) if c == config & MCP342x._resolution_mask][0]

    @staticmethod
    def config_to_lsb(config):
        return MCP342x._resolution_to_lsb[MCP342x.config_to_resolution(config)]

    @staticmethod
    def config_to_str(config, width=8):
        n = config & 0x7f
        s = bin(n)[2:]
        return '0b' + ('0' * (width-len(s))) + s

    @staticmethod
    def configure_device(bus, address, config):
        logger.debug('Configure device ' + hex(address))
        bus.write_byte(address, config)

    @staticmethod
    def convert_and_read_many(adcs, 
                              samples=None, 
                              aggregate=None, 
                              raw=False):
        # Group the sampling into batches with different device
        # addresses (cannot simultaneously sample from different
        # channels of the same device). Devices may not all be on the
        # same bus.
        batches = {}           # dict of lists
        addresses = {}         # dict of lists
        position = {}          # dict of lists
        unique_addresses = {}  # dict of dicts
        num_batches = 0
        pn = -1
        for a in adcs:
            pn += 1
            bus = a.get_bus()
            if bus not in batches:
                batches[bus] = []
                addresses[bus] = []
                position[bus] = []
                unique_addresses[bus] = {}
            done = False
            # Check if this sampling can be done with one of the
            # existing batches of sampling
            for n in range(len(addresses[bus])):
                if a.get_address() not in addresses[bus][n]:
                    # Use existing batch
                    batches[bus][n].append(a)
                    addresses[bus][n].append(a.get_address())
                    position[bus][n].append(pn)
                    unique_addresses[bus][a.get_address()] = None
                    done = True
                    break
            if not done:
                # Must start a new batch
                batches[bus].append([a])
                addresses[bus].append([a.get_address()])
                position[bus].append([pn])
                unique_addresses[bus][a.get_address()] = None
                # Remember highest numbered batch across all buses
                num_batches = max(num_batches, len(batches[bus]))
        
        if samples is not None:
            # Must avoid duplicating the same list when initializing!
            results = [[0] * samples for _ in range(len(adcs))]
        else:
            results = [0] * len(adcs)

        for sn in ([0] if samples is None else range(samples)):
            # Configure all devices from each batch, for each bus. Issues
            # general_call_convert for all buses then read back the
            # results from each batch.
            for bn in range(num_batches):
                # Configure
                for bus in batches:
                    if bn < len(batches[bus]):
                        unconfigured_devices = {
                            key: None for key in unique_addresses[bus]}
                        for a in batches[bus][bn]:
                            a.configure()
                            del unconfigured_devices[a.get_address()]
                        # Configure unused devices for 12-bit sampling so
                        # that we aren't waiting for them to complete
                        # sampling later
                        for addr in unconfigured_devices:
                            MCP342x.configure_device(bus, addr, 0)

                # Convert
                for bus in batches:
                    if bn < len(batches[bus]):
                        MCP342x.general_call_convert(bus)

                # Read results
                for bus in batches:
                    if bn < len(batches[bus]):
                        for n in range(len(batches[bus][bn])):
                            a = batches[bus][bn][n]
                            pn = position[bus][bn][n]
                            if samples:
                                results[pn][sn] = a.read(raw=raw)
                            else:
                                results[pn] = a.read(raw=raw)

        if aggregate:
            for pn in range(len(adcs)):
                results[pn] = aggregate(results[pn])
        return results

    def __init__(self, 
                 bus, 
                 address, 
                 device='MCP3424', 
                 channel=0, 
                 gain=1, 
                 resolution=12, 
                 continuous_mode=False, 
                 scale_factor=1.0,
                 offset=0.0):

        if device not in ('MCP3422', 'MCP3423', 'MCP3424', 
                          'MCP3426', 'MCP3427', 'MCP3428'):
            raise Exception('Unknown device: ' + str(device))
        self.bus = bus
        self.address = address
        self.config = 0
        self.device = device
        self.scale_factor = scale_factor
        self.offset = offset

        self.set_channel(channel)
        self.set_gain(gain)
        self.set_resolution(resolution)
        self.set_continuous_mode(continuous_mode)

    def __repr__(self):
        addr = hex(self.address)
        return (type(self).__name__ + ': device=' + self.device 
                + ', address=' + addr)

    def get_bus(self):
        return self.bus

    def get_address(self):
        return self.address

    def get_gain(self):
        return MCP342x.config_to_gain(self.config)

    def get_resolution(self):
        return MCP342x.config_to_resolution(self.config)

    def get_continuous_mode(self):
        return bool(self.config & MCP342x._continuous_mode_mask)

    def get_channel(self):
        return [g for g, c in iter(MCP342x._channel_to_config.items()) if c == self.config & MCP342x._channel_mask][0]

    def get_config(self):
        return self.config

    def get_scale_factor(self):
        return self.scale_factor

    def get_offset(self):
        return self.offset

    # def set_bus(self, bus):
    #     # bus = self.bus
    #     self.bus = bus

    def set_address(self, address):
        self.address = address

    def set_gain(self, gain):
        if gain not in MCP342x._gain_to_config:
            raise Exception('Illegal gain')

        self.config &= (~MCP342x._gain_mask & 0x7f)
        self.config |= MCP342x._gain_to_config[gain]

    def set_resolution(self, resolution):
        if resolution not in MCP342x._resolution_to_config:
            raise Exception('Illegal resolution')
        elif resolution == 18 and \
                self.device not in ('MCP3422', 'MCP3423', 'MCP3424'):
            raise Exception('18 bit sampling not suuported by ' +
                            self.device)
            
        self.config &= (~MCP342x._resolution_mask & 0x7f)
        self.config |= MCP342x._resolution_to_config[resolution]

    def set_continuous_mode(self, continuous_mode):
        if continuous_mode:
            self.config |= MCP342x._continuous_mode_mask
        else:
            self.config &= (~MCP342x._continuous_mode_mask & 0x7f)

    def set_channel(self, channel):
        if channel not in MCP342x._channel_to_config:
            raise Exception('Illegal channel')
        elif channel in (2, 3) and \
                self.device not in ('MCP3424', 'MCP3428'):
            raise Exception('Channel ' + str(channel) + 
                            ' not supported by ' + self.device)

        self.config &= (~MCP342x._channel_mask & 0x7f)
        self.config |= MCP342x._channel_to_config[channel]

    def set_scale_factor(self, scale_factor):
        self.scale_factor = scale_factor

    def set_offset(self, offset):
        self.offset = offset

    def set_config(self, config):
        self.config = config & 0x7f

    def get_conversion_time(self):
        return MCP342x._conversion_time[self.get_resolution()] 

    def configure(self):
        """Configure the device.

        Send the device configuration saved inside the MCP342x object to the target device."""
        logger.debug('Configuring ' + hex(self.get_address())
                     + ' ch: ' + str(self.get_channel())
                     + ' res: ' + str(self.get_resolution())
                     + ' gain: ' + str(self.get_gain()))
        self.bus.write_byte(self.address, self.config)

    def convert(self):
        """Initiate one-shot conversion.

        The current settings are used, with the exception of continuous mode."""
        c = self.config
        c &= (~MCP342x._continuous_mode_mask & 0x7f)  # Force one-shot
        c |= MCP342x._not_ready_mask                  # Convert
        logger.debug('Convert ' + hex(self.address) + ' config: ' + bin(c))
        self.bus.write_byte(self.address, c)

    def raw_read(self):
        res = self.get_resolution()
        bytes_to_read = 4 if res == 18 else 3
        while True:
            # Stupid smbus forces us to write a byte of data, even
            # with its 'I2C' write command. For MCP342x this forces us
            # to overwrite the configuration setting.
            #
            # The correct action would be to check the configuration
            # reported by raw_read() matches the stored configuration
            # in the object. This can't be done since we have to
            # destroy the actual value before reading.
            d = self.bus.read_i2c_block_data(self.address, 
                                             self.config, 
                                             bytes_to_read)
            config_used = d[-1]
            if config_used & MCP342x._not_ready_mask == 0:
                count = 0
                for i in range(bytes_to_read - 1):
                    count <<= 8
                    count |= d[i]

                sign_bit_mask = 1 << (res - 1)
                count_mask = sign_bit_mask - 1
                sign_bit = count & sign_bit_mask
                count &= count_mask
                if sign_bit:
                    count = -(~count & count_mask) - 1
                
                return count, config_used
                    
    def read(self, scale_factor=None, offset=None, raw=False):
        if scale_factor is None:
            scale_factor = self.scale_factor
        if offset is None:
            offset = self.offset
        count, config_used = self.raw_read()
        # Go through the motions of checking that the configuration
        # matches. Until raw_read() is able to read without
        # overwriting the configuration setting this is unlikely to be
        # very useful.
        if config_used != self.config:
            raise Exception('Config does not match ('
                            + MCP342x.config_to_str(config_used) + ' != ' 
                            + MCP342x.config_to_str(self.config))
        
        if raw:
            return count
        lsb = MCP342x.config_to_lsb(config_used)
        # With the standard scale_factor=1 this returns the voltage
        # difference between IN+ and IN-. Other scale_factors can be
        # used to account for gain or attenuation, or to convert
        # voltage to some sensor input value.
        voltage = (count * lsb * scale_factor / MCP342x.config_to_gain(config_used)) + offset
        return voltage

    def convert_and_read(self, 
                         sleep=True, 
                         samples=None,
                         aggregate=None,
                         **kwargs):
        if samples is not None:
            r = [0] * samples
        for sn in ([0] if samples is None else range(samples)):
            self.convert()
            if sleep:
                time.sleep(0.95 * self.get_conversion_time())
            val = self.read(**kwargs)
            if samples is not None:
                r[sn] = val
            else:
                r = val
        if aggregate:
            r = aggregate(r)
        return r


logger = logging.getLogger(__name__)
