
#####################################################
# Import Packages and initialise Logger             #
#####################################################

import logging, json, string, requests, time, random, urllib3

import voluptuous as vol

from requests.auth import HTTPDigestAuth
from requests.adapters import HTTPAdapter

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import dispatcher_connect
from homeassistant.helpers.event import track_state_change
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.switch import (DOMAIN, PLATFORM_SCHEMA, SwitchEntity, ENTITY_ID_FORMAT)
from homeassistant.const import (ATTR_ENTITY_ID, CONF_HOST, CONF_NAME, CONF_PLATFORM, CONF_ENTITY_ID, CONF_USERNAME, CONF_PASSWORD, CONF_ADDRESS, CONF_DISPLAY_OPTIONS, STATE_ON, STATE_OFF, STATE_STANDBY, SERVICE_TURN_ON)
from homeassistant.components.light import (is_on, ATTR_BRIGHTNESS, ATTR_COLOR_TEMP, ATTR_RGB_COLOR, ATTR_TRANSITION,VALID_TRANSITION, ATTR_WHITE_VALUE, ATTR_XY_COLOR, DOMAIN as LIGHT_DOMAIN)
from homeassistant.util import slugify

#####################################################
# Set default Variables                             #
#####################################################

ICON = 'mdi:television-ambient-light'

DEFAULT_NAME = 'OldAmbilights+Hue'
DEFAULT_RGB_COLOR = [255,137,14] # default colour for bulb when dimmed in game mode (and incase of failure)
DEFAULT_HOST = '127.0.0.1'
DEFAULT_ENTITY_ID = "entity_id"
DEFAULT_DISPLAY_OPTIONS = 'right'
BASE_URL = 'http://{0}:1925/1/{1}'
TIMEOUT = 60.0 # get/post request timeout with tv
CONNFAILCOUNT = 5 # number of get/post attempts

#####################################################
# Define Platform Schema and Setup                  #
#####################################################

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
	vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
	vol.Required(CONF_HOST, default=DEFAULT_HOST): cv.string,
	vol.Required(CONF_ENTITY_ID, default=DEFAULT_ENTITY_ID): cv.entity_id,
	vol.Required(CONF_DISPLAY_OPTIONS, default=DEFAULT_DISPLAY_OPTIONS): cv.string
})

def setup_platform(hass, config, add_devices, discovery_info=None):
	name = config.get(CONF_NAME)
	tvip = config.get(CONF_HOST)
	bulb = config.get(CONF_ENTITY_ID)
	position = config.get(CONF_DISPLAY_OPTIONS)
	add_devices([OldAmbiHue(name, tvip, bulb, position)])

#####################################################
# Define and initiate AmiHue Class                  #
#####################################################

class OldAmbiHue(SwitchEntity):

    def __init__(self, name, tvip, bulb, position):
        self._name = name
        self._icon = ICON
        self._tvip = tvip
        self._bulb = bulb
        self._position = position
        self._state = False
        self._connfail = 0
        self._attributes = {}
        self._attributes['position'] = position
        self._attributes['r'] = None
        self._attributes['g'] = None
        self._attributes['b'] = None
        self._attributes['tvip'] = tvip
        self._session = requests.Session()
        self._session.mount('http://', HTTPAdapter(pool_connections=1))

    @property
    def name(self):
        """Name to use in the frontend, if any."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._state

    async def async_added_to_hass(self):
        """Call when entity about to be added to hass."""
        # If not None, we got an initial value.
        await super().async_added_to_hass()
        if self._state is not None:
            return

        state = await self.async_get_last_state()
        self._state = state and state.state == STATE_ON

    @property
    def device_state_attributes(self):
        """Return the state attributes of the monitored values."""
        return self._attributes

    @property
    def should_poll(self):
        return False

#####################################################
# Define Bulb Turn On Function                      #
#####################################################

    def turn_on(self, **kwargs):
        """Turn on the switch."""
        self._state = True
        self._follow = True
        self.follow_tv(self._position, 0.05) # 0.05ms is the 'sleep' time between refresh cycles
        self.async_schedule_update_ha_state()

#####################################################
# Define Bulb Turn Off Function                     #
#####################################################

    def turn_off(self, **kwargs):
        """Turn off the switch."""
        self._state = False
        self._follow = False
        self._attributes['r'] = None
        self._attributes['g'] = None
        self._attributes['b'] = None
        self.async_schedule_update_ha_state()

#####################################################
# Define Follow TV Function                         #
#####################################################

    def follow_tv(self, position, sleep): 
        while self._follow == True: # main loop for updating the bulb
            try:
                ambivalues = self._session.get(BASE_URL.format(self._tvip, 'ambilight/processed'), verify=False, timeout=TIMEOUT)
                ambivalues = json.loads(ambivalues.text)
                layer1 = ambivalues['layer1']

                pixels = layer1['right']
                pixel = str(int(len(pixels)/2))
                r = int(pixels[pixel]['r'])
                g = int(pixels[pixel]['g'])
                b = int(pixels[pixel]['b'])

                print("Got the Ambilight RGB values from this URL:", BASE_URL.format(self._tvip, 'ambilight/processed'))
                print("Ambilight red:", r)
                print("Ambilight green:", g)
                print("Ambilight blue:", b)
                self._attributes['r'] = r
                self._attributes['g'] = g
                self._attributes['b'] = b
                self.async_schedule_update_ha_state()

                time.sleep(sleep)
            except:
                print("Getting Ambilight RGB Values Failed")
                time.sleep(sleep)

