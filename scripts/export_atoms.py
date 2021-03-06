import logging
import os
from astropy.time import Time, TimeDelta
import astropy.units as u
from common.minimodel import ALL_SITES, ObservationClass, ProgramTypes, Semester, SemesterHalf
from api.programprovider.ocs import read_ocs_zipfile, OcsProgramProvider
from common.output import atoms_to_sheet
from components.collector import Collector


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # Read in a list of JSON data
    programs = read_ocs_zipfile(os.path.join('..', 'data', '2018B_program_samples.zip'))

    # Create the Collector and load the programs.
    collector = Collector(
        start_time=Time("2018-10-01 08:00:00", format='iso', scale='utc'),
        end_time=Time("2018-10-03 08:00:00", format='iso', scale='utc'),
        time_slot_length=TimeDelta(1.0 * u.min),
        sites=ALL_SITES,
        semesters={Semester(2018, SemesterHalf.B)},
        program_types={ProgramTypes.Q, ProgramTypes.LP, ProgramTypes.FT, ProgramTypes.DD},
        obs_classes={ObservationClass.SCIENCE, ObservationClass.PROGCAL, ObservationClass.PARTNERCAL}
    )
    collector.load_programs(program_provider=OcsProgramProvider(),
                            data=programs)

    # Output the state of and information calculated by the Collector.
    # print_collector_info(collector, samples=60)
    
    # Output the data in a spreadsheet.
    for program in collector.get_program_ids():
        if program == 'GS-2018B-Q-101':
            atoms_to_sheet(collector.get_program(program))
