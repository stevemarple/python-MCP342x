"""Access Microchip MCP342x analogue to digital converters."""

__author__ = 'Steve Marple'
__version__ = '0.0.1'
__license__ = 'PSF'

import logging

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
    def get_gain2(config):
        return [g for g,c in MCP342x._gain_to_config.iteritems() \
                    if c == config & MCP342x._gain_mask][0]

    def __init__(self, bus, address, device='MCP3424'):
        self.bus = bus
        self.address = address
        self.config = 0
        self.device = device

        
    def __repr__(self):
        addr = hex(self.address)
        return (type(self).__name__ + ': device=' + self.device 
                + ', address=' + addr)

    def get_gain(self):
        return [g for g,c in MCP342x._gain_to_config.iteritems() \
                    if c == self.config & MCP342x._gain_mask][0]

    def get_resolution(self):
        return [g for g,c in MCP342x._resolution_to_config.iteritems() \
                    if c == self.config & MCP342x._resolution_mask][0]

    def get_continuous_mode(self):
        return bool(self.config & MCP342x._continuous_mode_mask)

    def get_channel(self):
        return [g for g,c in MCP342x._channel_to_config.iteritems() \
                    if c == self.config & MCP342x._channel_mask][0]

    def set_gain(self, gain):
        if gain not in MCP342x._gain_to_config:
            raise Exception('Illegal gain')

        self.config &= (~MCP342x._gain_mask & 0x7f)
        self.config |= MCP342x._gain_to_config[gain]

    def set_resolution(self, resolution):
        if resolution not in MCP342x._resolution_to_config:
            raise Exception('Illegal resolution')

        self.config &= (~MCP342x._resolution_mask & 0x7f)
        self.config |= MCP342x._resolution_to_config[resolution]

    def set_continuous_mode(self, continuous):
        if continuous:
            self.config |= MCP342x._continuous_mode_mask
        else:
            self.config &= (~MCP342x._continuous_mode_mask & 0x7f)

    def set_channel(self, channel):
        if channel not in _channel_to_config:
            raise Exception('Illegal channel')

        self.config &= (~MCP342x._channel_mask & 0x7f)
        self.config |= MCP342x._channel_to_config[channel]

    def get_config(self):
        return self.config

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
        
    def convert_and_read(self):
        self.convert()
        res = self.get_resolution()
        bytes_to_read = 4 if res == 18 else 3
        while True:
            d = self.bus.read_i2c_block_data(self.address, self.config, 
                                             bytes_to_read)
            config_used = d[-1]
            if config_used & MCP342x._not_ready_mask == 0:
                data = 0
                for i in range(bytes_to_read - 1):
                    data <<= 8
                    data |= d[i]
                # data_mask = (1 << res) - 1
                sign_bit_mask = 1 << (res - 1)
                data_mask = sign_bit_mask - 1
                sign_bit = data & sign_bit_mask
                data &= data_mask
                if sign_bit:
                    data = -(~data & data_mask) - 1
                
                # Correct for gain
                data = data / float(MCP342x.get_gain2(config_used))
                return data, config_used
                    

        
