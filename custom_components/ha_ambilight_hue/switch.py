
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

_LOGGER = logging.getLogger(__name__)

ICON = 'mdi:television-ambient-light'

DEFAULT_NAME = 'OldAmbilightsHue'
DEFAULT_RGB_COLOR = [255,137,14] # default colour for bulb when dimmed in game mode (and incase of failure)
DEFAULT_HOST = '127.0.0.1'
DEFAULT_ENTITY_ID = "entity_id"
DEFAULT_DISPLAY_OPTIONS = 'right'
BASE_URL = 'http://{0}:1925/1/{1}'
TIMEOUT = 5 # get/post request timeout with tv
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
        self._attributes['tvip'] = tvip
        self._attributes['light'] = bulb
        self._attributes['position'] = position
        self._attributes['RGB'] = None
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

    def turn_on(self, **kwargs) -> None:
        """Turn on the switch."""
        _LOGGER.debug(self._name + " turned on")
        self._state = True
        self.follow_tv(self._position, 0.05) # 0.05ms is the 'sleep' time between refresh cycles
        self.schedule_update_ha_state()

#####################################################
# Define Bulb Turn Off Function                     #
#####################################################

    def turn_off(self, **kwargs):
        """Turn off the switch."""
        _LOGGER.debug(self._name + " turned off")
        self._state = False
        self.schedule_update_ha_state(force_refresh=True)
        self._attributes['RGB'] = None

#####################################################
# Define Follow TV Function                         #
#####################################################

    def follow_tv(self, position, sleep): 
        while self._state == True: # main loop for updating the bulb
            try:
                ambivalues = self._session.get(BASE_URL.format(self._tvip, 'ambilight/processed'), verify=False, timeout=TIMEOUT)
                ambivalues = json.loads(ambivalues.text)
                layer1 = ambivalues['layer1']

            ##############################################
            # Calculate RGB Values depending on position #
            ##############################################

                if position == 'top-middle-average': # 'display_options' value given in home assistant 
                    pixels = layer1['top'] # for tv topology see http://jointspace.sourceforge.net/projectdata/documentation/jasonApi/1/doc/API-Method-ambilight-topology-GET.html
                    pixel3 = str((int(len(pixels)/2)-1)) # selects pixels
                    pixel4 = str(int(len(pixels)/2))
                    r = int( ((pixels[pixel3]['r'])**2+(pixels[pixel4]['r'])**2) ** (1/2) )
                    g = int( ((pixels[pixel3]['g'])**2+(pixels[pixel4]['g'])**2) ** (1/2) )
                    b = int( ((pixels[pixel3]['b'])**2+(pixels[pixel4]['b'])**2) ** (1/2) )
                elif position == 'top-average':
                    pixels = layer1['top']
                    r_sum, g_sum, b_sum = 0,0,0
                    for pixel in pixels:
                        r_sum = r_sum + ((pixel['r']) ** 2)
                        g_sum = g_sum + ((pixel['g']) ** 2)
                        b_sum = b_sum + ((pixel['b']) ** 2)
                    r = int((r_sum/len(pixels))*(1/2))
                    g = int((g_sum/len(pixels))*(1/2))
                    b = int((b_sum/len(pixels))*(1/2))
                elif position == 'right-average':
                    pixels = layer1['right']
                    r_sum, g_sum, b_sum = 0,0,0
                    for i in range(0,len(pixels)):
                        pixel = str(int(i))
                        r_sum = r_sum + ((pixels[pixel]['r']) ** 2)
                        g_sum = g_sum + ((pixels[pixel]['g']) ** 2)
                        b_sum = b_sum + ((pixels[pixel]['b']) ** 2)
                    r = int((r_sum/len(pixels))**(1/2))
                    g = int((g_sum/len(pixels))**(1/2))
                    b = int((b_sum/len(pixels))**(1/2))
                elif position == 'left-average':
                    pixels = layer1['left']
                    r_sum, g_sum, b_sum = 0,0,0
                    for pixel in pixels:
                        r_sum = r_sum + ((pixel['r']) ** 2)
                        g_sum = g_sum + ((pixel['g']) ** 2)
                        b_sum = b_sum + ((pixel['b']) ** 2)
                    r = int((r_sum/len(pixels))*(1/2))
                    g = int((g_sum/len(pixels))*(1/2))
                    b = int((b_sum/len(pixels))*(1/2))
                elif position == 'bottom-average':
                    pixels = layer1['bottom']
                    r_sum, g_sum, b_sum = 0,0,0
                    for pixel in pixels:
                        r_sum = r_sum + ((pixel['r']) ** 2)
                        g_sum = g_sum + ((pixel['g']) ** 2)
                        b_sum = b_sum + ((pixel['b']) ** 2)
                    r = int((r_sum/len(pixels))*(1/2))
                    g = int((g_sum/len(pixels))*(1/2))
                    b = int((b_sum/len(pixels))*(1/2))
                elif position == 'top-middle' or position == 'top-center' or position == 'top':
                    pixels = layer1['top']
                    pixel = str(int(len(pixels)/2))
                    r = int(pixels[pixel]['r'])
                    g = int(pixels[pixel]['g'])
                    b = int(pixels[pixel]['b'])
                elif position == 'bottom-middle' or position == 'bottom-center' or position == 'bottom':
                    pixels = layer1['bottom']
                    pixel = str(int(len(pixels)/2))
                    r = int(pixels[pixel]['r'])
                    g = int(pixels[pixel]['g'])
                    b = int(pixels[pixel]['b'])
                elif position == 'right':
                    pixels = layer1['right']
                    pixel = str(int(len(pixels)/2))
                    r = int(pixels[pixel]['r'])
                    g = int(pixels[pixel]['g'])
                    b = int(pixels[pixel]['b'])
                elif position == 'left':
                    pixels = layer1['left']
                    pixel = str(int(len(pixels)/2))
                    r = int(pixels[pixel]['r'])
                    g = int(pixels[pixel]['g'])
                    b = int(pixels[pixel]['b'])
                elif position == 'top-right-average':
                    r_sum, g_sum, b_sum = 0,0,0
                    rightpixels = layer1['right']
                    rtpixel = rightpixels['0']
                    toppixels = layer1['top']
                    trpixel = toppixels[str(int(len(toppixels)-1))]
                    selected_pixels = [rtpixel,trpixel]
                    for pixel in selected_pixels:
                        r_sum = r_sum + ((pixel['r']) ** 2)
                        g_sum = g_sum + ((pixel['g']) ** 2)
                        b_sum = b_sum + ((pixel['b']) ** 2)
                    r = int((r_sum/len(selected_pixels))*(1/2))
                    g = int((g_sum/len(selected_pixels))*(1/2))
                    b = int((b_sum/len(selected_pixels))*(1/2))
                elif position == 'top-left-average':
                    r_sum, g_sum, b_sum = 0,0,0
                    leftpixels = layer1['left']
                    ltpixel = leftpixels[str(int(len(leftpixels)-1))]
                    toppixels = layer1['top']
                    tlpixel = toppixels['0']
                    selected_pixels = [ltpixel,tlpixel]
                    for pixel in selected_pixels:
                        r_sum = r_sum + ((pixel['r']) ** 2)
                        g_sum = g_sum + ((pixel['g']) ** 2)
                        b_sum = b_sum + ((pixel['b']) ** 2)
                    r = int((r_sum/len(selected_pixels))*(1/2))
                    g = int((g_sum/len(selected_pixels))*(1/2))
                    b = int((b_sum/len(selected_pixels))*(1/2))
                elif position == 'bottom-right-average':
                    r_sum, g_sum, b_sum = 0,0,0
                    rightpixels = layer1['right']
                    rbpixel = rightpixels[str(int(len(rightpixels)-1))]
                    bottompixels = layer1['bottom']
                    rbpixel = bottompixels[str(int(len(bottompixels)-1))]
                    selected_pixels = [rbpixel,brpixel]
                    for pixel in selected_pixels:
                        r_sum = r_sum + ((pixel['r']) ** 2)
                        g_sum = g_sum + ((pixel['g']) ** 2)
                        b_sum = b_sum + ((pixel['b']) ** 2)
                    r = int((r_sum/len(selected_pixels))*(1/2))
                    g = int((g_sum/len(selected_pixels))*(1/2))
                    b = int((b_sum/len(selected_pixels))*(1/2))
                elif position == 'bottom-left-average':
                    r_sum, g_sum, b_sum = 0,0,0
                    leftixels = layer1['left']
                    lbpixel = leftixels['0']
                    bottompixels = layer1['bottom']
                    blpixel = bottomixels['0']
                    selected_pixels = [lbpixel,blpixel]
                    for pixel in selected_pixels:
                        r_sum = r_sum + ((pixel['r']) ** 2)
                        g_sum = g_sum + ((pixel['g']) ** 2)
                        b_sum = b_sum + ((pixel['b']) ** 2)
                    r = int((r_sum/len(selected_pixels))*(1/2))
                    g = int((g_sum/len(selected_pixels))*(1/2))
                    b = int((b_sum/len(selected_pixels))*(1/2))
                elif position == 'right-top':
                    pixels = layer1['right']
                    r = int(pixels['0']['r'])
                    g = int(pixels['0']['g'])
                    b = int(pixels['0']['b'])
                elif position == 'left-top':
                    pixels = layer1['left']
                    pixel = str(int(len(pixels)-1))
                    r = int(pixels[pixel]['r'])
                    g = int(pixels[pixel]['g'])
                    b = int(pixels[pixel]['b'])
                elif position == 'top-left':
                    pixels = layer1['top']
                    r = int(pixels['0']['r'])
                    g = int(pixels['0']['g'])
                    b = int(pixels['0']['b'])
                elif position == 'top-right':
                    pixels = layer1['top']
                    pixel = str(int(len(pixels)-1))
                    r = int(pixels[pixel]['r'])
                    g = int(pixels[pixel]['g'])
                    b = int(pixels[pixel]['b'])
                elif position == 'right-bottom':
                    pixels = layer1['right']
                    pixel = str(int(len(pixels)-1))
                    r = int(pixels[pixel]['r'])
                    g = int(pixels[pixel]['g'])
                    b = int(pixels[pixel]['b'])
                elif position == 'left-bottom':
                    pixels = layer1['left']
                    r = int(pixels['0']['r'])
                    g = int(pixels['0']['g'])
                    b = int(pixels['0']['b'])
                elif position == 'bottom-left':
                    pixels = layer1['bottom']
                    r = int(pixels['0']['r'])
                    g = int(pixels['0']['g'])
                    b = int(pixels['0']['b'])
                elif position == 'bottom-right':
                    pixels = layer1['bottom']
                    pixel = str(int(len(pixels)-1))
                    r = int(pixels[pixel]['r'])
                    g = int(pixels[pixel]['g'])
                    b = int(pixels[pixel]['b'])

                _LOGGER.debug(self._name + " got RGB values from " + BASE_URL.format(self._tvip, 'ambilight/processed'))
                self._attributes['RGB'] = r, g, b
                self.schedule_update_ha_state()

            #################################################
            # Sending calculated RGB Values to Light Entity #
            #################################################

                if r == None and g == None and b == None:
                    service_data = {ATTR_ENTITY_ID: self._bulb}
                    service_data[ATTR_RGB_COLOR] = tuple(map(int, (255,255,255)))
                    service_data[ATTR_BRIGHTNESS] = 0
                    service_data[ATTR_TRANSITION] = 5
                    self.hass.services.call(LIGHT_DOMAIN, SERVICE_TURN_ON, service_data)
                    _LOGGER.debug(self._bulb + self._name + " RGB Adjusted - rgb_color: " + str(rgb) + ", brightness: " + str(brightness) + ", transition: " + str(transition))
                else:
                    service_data = {ATTR_ENTITY_ID: self._bulb}
                    service_data[ATTR_RGB_COLOR] = tuple(map(int, (r,g,b)))
                    service_data[ATTR_BRIGHTNESS] = 50
                    service_data[ATTR_TRANSITION] = 5
                    self.hass.services.call(LIGHT_DOMAIN, SERVICE_TURN_ON, service_data)
                    _LOGGER.debug(self._bulb + self._name + " RGB Adjusted - rgb_color: " + str(rgb) + ", brightness: " + str(brightness) + ", transition: " + str(transition))

                time.sleep(sleep)
            except:
                _LOGGER.debug("Getting Ambilight RGB Values for " + self._name + " failed")
                #self.turn_off() # Switch will turn emidiatly off when this activated?
