from dataclasses import dataclass
from datetime import datetime, timedelta
import dateutil.parser
from common.minimodel import Target, TargetTag, Site
from common.helpers.helpers import dms2rad, hms2rad
import numpy as np
import numpy.typing as npt
import requests
from typing import Tuple, Union, List
import logging
import contextlib
import os


@dataclass
class Angle:
    """
    Angle in radians.
    """
    µasPerDegree: float =  60 * 1000

    @staticmethod
    def to_signed_microarcseconds(angle: float) -> float:
        """
        Convert an angle in radians to a signed microarcsecond angle.
        """
        degrees = Angle.to_degrees(angle)
        if degrees > 180:
            degrees -= 360
        return degrees * Angle.µasPerDegree
 
    def to_degrees(angle: float) -> float:
        """
        Convert an angle in radians to a signed degree angle.
        """
        return angle * 180.0 / np.pi

    @staticmethod
    def to_microarcseconds(angle: float) -> float:
        """
        Convert an angle in radians to a signed microarcsecond angle.
        """
        return Angle.to_degrees(angle) * Angle.µasPerDegree

class Coordinates:
    """
    Both ra and dec are in radians.

    """
    def __init__(self, ra: float, dec: float) -> None:
        
        self.ra = ra
        self.dec = dec

    def angular_distance(self, other: 'Coordinates') -> float:
        """
        Calculate the angular distance between two points on the sky.
        based on
        https://github.com/gemini-hlsw/lucuma-core/blob/master/modules/core/shared/src/main/scala/lucuma/core/math/Coordinates.scala#L52
        """
        φ1 = self.dec
        φ2 = other.dec
        delta_φ = other.dec - self.dec
        delta_λ = other.ra - self.ra
        a = np.sin(delta_φ / 2)**2 + np.cos(φ1) * np.cos(φ2) * np.sin(delta_λ / 2)**2

        if a >= 0 and a <= 1:
            return 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
        else:
            return 0.0 # TODO: Temporary bypass for negative values in sqrt 
 
    def interpolate(self, other: 'Coordinates', f: float) -> 'Coordinates':
        """
        Interpolate between two Coordinates objects.
        """

        delta = self.angular_distance(other)
        if delta == 0:
            return Coordinates(self.ra, self.dec)
        else:
            a = np.sin((1 - f) * delta) / np.sin(delta)
            b = np.sin(f * delta) / np.sin(delta)
            x = a * np.cos(self.dec) * np.cos(self.ra) + b * np.cos(other.dec) * np.cos(other.ra)
            y = a * np.cos(self.dec) * np.sin(self.ra) + b * np.cos(other.dec) * np.sin(other.ra)
            z = a * np.sin(self.dec) + b * np.sin(other.dec)
            φi = np.arctan2(z, np.sqrt(x * x + y * y))
            λi = np.arctan2(y, x)
            return Coordinates(λi, φi)
    
    def __repr__(self) -> str:
        return f'Coordinates(ra={self.ra}, dec={self.dec})'


@dataclass
class EphemerisCoordinates:
    """
    Both ra and dec are in radians.

    """
    coordinates: List[Coordinates]
    times: npt.NDArray[float]

    def _bracket(self, time: datetime) -> Tuple[datetime, datetime]:
        """
        Return both lower and upper of the given time: i.e., the closest elements on either side. 
        """
        return self.times[self.times > time].min(), self.times[self.times < time].max()

    def interpolate(self, time: datetime) ->  Coordinates:
        """
        Interpolate ephemeris to a given time.
        """
        a, b = self._bracket(time)
        # Find indexes for each bound
        i_a, i_b = np.where(self.time == a)[0][0], np.where(self.time == b)[0][0]
        factor = (time.timestamp() - a.timestamp() / b.timestamp() - a.timestamp()) * 1000
        logging.info(f'Interpolating by factor: {factor}')

        return self.coordinates[i_a].interpolate(self.coordinates[i_b], factor)


class HorizonsClient:
    """
    API to interact with the Horizons service
    """

    # A not-complete list of solar system major body Horizons IDs
    bodies = {'mercury': '199', 'venus': '299', 'mars': '499', 'jupiter': '599', 'saturn': '699',
               'uranus': '799', 'neptune': '899', 'pluto': '999', 'io': '501'}

    FILE_DATE_FORMAT = '%Y%m%d_%H%M'

    def __init__(self,
                 site: Site,
                 path: str = os.path.join('horizons', 'data'),
                 airmass: int = 3,
                 start: datetime = None,
                 end: datetime = None):
        self.path = path
        self.url = 'https://ssd.jpl.nasa.gov/horizons_batch.cgi'
        self.start = start
        self.end = end
        self.airmass = airmass
        self.site = site
     
    
    @staticmethod
    def generate_horizons_id(designation: str) -> str:
        des = designation.lower()
        return HorizonsClient.bodies[des] if des in HorizonsClient.bodies else designation

    def _time_bounds(self) -> Tuple[str, str]:
        """
        Returns the start and end times based on the given date
        """
        return self.start.strftime(HorizonsClient.FILE_DATE_FORMAT), self.end.strftime(HorizonsClient.FILE_DATE_FORMAT)
    
    def _form_horizons_name(self, tag: TargetTag, designation: str) -> str:
        """
        Formats the name of the body
        """
        if tag is TargetTag.COMET:
            name = f'DES={designation};CAP'
        elif tag is TargetTag.ASTEROID:
            name = f'DES={designation};'
        else:
            name = self.generate_horizons_id(designation)
        return name

    def _get_ephemeris_file(self, name: str) -> str:
        """
        Returns the ephemeris file name
        """
        start, end = self._time_bounds()
        return os.path.join(self.path, f"{self.site.name}_{name.replace(' ', '').replace('/', '')}_{start}-{end}.eph")
    
    def query(self,
              target: str,
              step: str = '1m',
              make_ephem: str = 'YES',
              cal_format: str = 'CAL',
              quantities: str = '1',
              object_data: str = 'NO',
              daytime: bool = False,
              csvformat: str = 'NO') -> requests.Response:
     
        # The items and order follow the JPL/Horizons batch example:
        # ftp://ssd.jpl.nasa.gov/pub/ssd/horizons_batch_example.long
        # and
        # ftp://ssd.jpl.nasa.gov/pub/ssd/horizons-batch-interface.txt
        # Note that spaces should be converted to '%20'
        
        skip_day = 'NO' if daytime else 'YES'

        center = self.site.value.coordinate_center

        params = {'batch':1}
        params['COMMAND']    = "'" + target + "'"
        params['OBJ_DATA']   = object_data # Toggles return of object summary data (YES or NO)
        params['MAKE_EPHEM'] = make_ephem # Toggles generation of ephemeris (YES or NO)
        params['TABLE_TYPE'] = 'OBSERVER'      # OBSERVER, ELEMENTS, VECTORS, or APPROACH 
        params['CENTER']     = center     # Set coordinate origin. MK=568, CP=I11, Earth=399
        params['REF_PLANE']  = None            # Table reference plane (ECLIPTIC, FRAME or BODY EQUATOR)
        params['COORD_TYPE'] = None            # Type of user coordinates in SITE_COORD
        params['SITE_COORD'] = None            # '0,0,0'
        
        # print(self.start.strftime("'%Y-%b-%d %H:%M'"))
        # print(self.end.strftime("'%Y-%b-%d %H:%M'"))
        params['START_TIME'] = self.start.strftime("'%Y-%b-%d %H:%M'")      # Ephemeris start time YYYY-MMM-DD {HH:MM} {UT/TT}
        params['STOP_TIME']  = self.end.strftime("'%Y-%b-%d %H:%M'")        # Ephemeris stop time YYYY-MMM-DD {HH:MM}
        params['STEP_SIZE']  = "'" + step + "'" # Ephemeris step: integer# {units} {mode}
        params['TLIST']      = None            # Ephemeris time list

        # This only works for small numbers (~<1000) of times:
        #tlist = ' '.join(map(str,numpy.arange(2457419.5, 2457600.0, 0.3)))
        #params['TLIST']      = tlist            # Ephemeris time list

        params['QUANTITIES'] = quantities # Desired output quantity codes
        params['REF_SYSTEM'] = 'J2000'         # Reference frame
        params['OUT_UNITS']  = None            # VEC: Output units
        params['VECT_TABLE'] = None            # VEC: Table format
        params['VECT_CORR']  = None            # VEC: correction level
        params['CAL_FORMAT'] = cal_format # OBS: Type of date output (CAL, JD, BOTH)
        params['ANG_FORMAT'] = 'HMS'           # OBS: Angle format (HMS or DEG)
        params['APPARENT']   = None            # OBS: Apparent coord refract corr (AIRLESS or REFRACTED)
        params['TIME_DIGITS'] = 'MINUTES'      # OBS: Precision (MINUTES, SECONDS, or FRACSEC)
        params['TIME_ZONE']  = None            # Local civil time offset relative to UT ('+00:00')
        params['RANGE_UNITS'] = None           # OBS: range units (AU or KM)
        params['SUPPRESS_RANGE_RATE'] = 'NO'   # OBS: turn off output of delta-dot and rdot
        params['ELEV_CUT']   = '-90'           # OBS: skip output when below elevation
        params['SKIP_DAYLT'] = skip_day   # OBS: skip output when daylight
        params['SOLAR_ELONG'] = "'0,180'"      # OBS: skip output outside range
        params['AIRMASS']    = self.airmass    # OBS: skip output when airmass is > cutoff
        params['LHA_CUTOFF'] = None            # OBS: skip output when hour angle is > cutoff
        params['EXTRA_PREC'] = 'YES'           # OBS: show additional output digits (YES or NO)
        params['CSV_FORMAT'] = csvformat  # Output in comma-separated value format (YES or NO)
        params['VEC_LABELS'] = None            # label each vector component (YES or NO)
        params['ELM_LABELS'] = None            # label each osculating element
        params['TP_TYPE']    = None            # Time of periapsis for osculating element tables
        params['R_T_S_ONLY'] = 'NO'            # Print only rise/transit/set (NO, TVH, GEO, RAD, YES)
        # Skiping the section of close-approch parameters...
        # Skiping the section of heliocentric ecliptic osculating elements...
        response = requests.get(self.url, params=params)

        return response

    def get_ephemerides(self,
                        target: Target,
                        overwrite: bool = False) -> EphemerisCoordinates:
 
        horizons_name = self._form_horizons_name(target.tag, target.des)
        logging.info(f'{target.des}')
        
        file = self._get_ephemeris_file(target.des) if target.tag is not TargetTag.MAJOR_BODY else self._get_ephemeris_file(horizons_name) 
        
        if not overwrite and os.path.exists(file):
            logging.info(f'Saving ephemerides file for {target.des}')
            with open(file, 'r') as f:
                lines = list(map(lambda x: x.strip('\n'), f.readlines()))
        else:
            logging.info(f'Querying JPL/Horizons for {horizons_name}')
            res = self.query(horizons_name)
            lines = res.text.splitlines()
            if file is not None:
                with open(file, 'w') as f:
                    f.write(res.text)

        time = np.array([])
        coords = []

        try:
            firstline = lines.index('$$SOE') + 1
            lastline = lines.index('$$EOE') - 1

            for line in lines[firstline:lastline]:
                if line and line[7:15] != 'Daylight' and line[7:14] != 'Airmass':

                    values = line.split(' ')
                    rah = int(values[-6])
                    ram = int(values[-5])
                    ras = float(values[-4])
                    decg = values[-3][0] # sign
                    decd = int(values[-3][1:3])
                    decm = int(values[-2])
                    decs = float(values[-1])

                    time = np.append(time, dateutil.parser.parse(line[1:18]))                    
                    coords.append(Coordinates(hms2rad([rah, ram, ras]), dms2rad([decd, decm, decs, decg])))

        except ValueError as e:
            logging.error(f'Error parsing ephemerides file for {target.des}')
            logging.error(e)
            raise e
        
        return EphemerisCoordinates(coords, time)

@contextlib.contextmanager
def horizons_session(site, start, end, airmass):
    client = HorizonsClient(site, start=start, end=end, airmass=airmass)
    try:
        yield client
    finally:
        del client
    return