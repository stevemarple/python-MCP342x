"""Access Microchip MCP342x analogue to digital converters."""

__author__ = 'Steve Marple'
__version__ = '0.2.0'
__license__ = 'PSF'

import logging
import time

logger = logging.getLogger(__name__)


class MCP342x(object):
    '''MCP342x class'''

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
        bus.write_byte(0, 6);
        return

    @staticmethod
    def general_call_latch(bus):
        bus.write_byte(0, 4);
        return

    @staticmethod
    def general_call_convert(bus):
        bus.write_byte(0, 8);
        return

    @staticmethod
    def config_to_gain(config):
        return [g for g,c in MCP342x._gain_to_config.iteritems() \
                    if c == config & MCP342x._gain_mask][0]

    @staticmethod
    def config_to_resolution(config):
        return [g for g,c in MCP342x._resolution_to_config.iteritems() \
                    if c == config & MCP342x._resolution_mask][0]

    @staticmethod
    def config_to_lsb(config):
        return MCP342x._resolution_to_lsb[MCP342x.config_to_resolution(config)]

    def __init__(self, bus, address, device='MCP3424', scale_factor=1.0):
        if device not in ('MCP3422', 'MCP3423', 'MCP3424', 
                          'MCP3426', 'MCP3427', 'MCP3428'):
            raise Exception('Unknown device: ' + str(device))
        self.bus = bus
        self.address = address
        self.config = 0
        self.device = device
        self.scale_factor = scale_factor
        
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
        return [g for g,c in MCP342x._channel_to_config.iteritems() \
                    if c == self.config & MCP342x._channel_mask][0]

    def get_config(self):
        return self.config


    def get_scale_factor(self):
        return self.scale_factor

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

    def set_continuous_mode(self, continuous):
        if continuous:
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

    def set_config(self, config):
        self.config = config & 0x7f

    def get_conversion_time(self):
        return MCP342x._conversion_time[self.get_resolution()] 

    def configure(self):
        '''Configure the device'''
        self.bus.write_byte(self.address, self.config)


    def convert(self):
        '''Initiate conversion with current settings.

        Applicable only to one-shot mode'''

        self.bus.write_byte(self.address, \
                                self.config | MCP342x._not_ready_mask)

        
    def raw_read(self):
        res = self.get_resolution()
        bytes_to_read = 4 if res == 18 else 3
        while True:
            d = self.bus.read_i2c_block_data(self.address, self.config, 
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
                    
    def read(self, scale_factor=None):
        if scale_factor is None:
            scale_factor = self.scale_factor
        count, config_used = self.raw_read()
        if config_used != self.config:
            raise Exception('Config does not match')
        lsb = MCP342x.config_to_lsb(config_used)
        voltage = count * lsb * scale_factor \
            / MCP342x.config_to_gain(config_used)
        return voltage
        
    def convert_and_read(self, sleep=True, samples=1, **kwargs):
        r = 0.0
        for n in range(samples):
            self.convert()
            if sleep:
                time.sleep(0.95 * self.get_conversion_time())
            r += self.read(**kwargs)
        return r / samples

