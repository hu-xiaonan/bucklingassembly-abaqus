# Copyright (C) 2021-2025, Hu Xiaonan
# License: MIT License

from abaqus import *
from abaqusConstants import *
import step

import numpy as np

# All my global constants start with the prefix `MY_` to prevent name
# duplication with Abaqus.

# Abaqus tends to convert some names to uppercase when storing them to ODB, so
# be careful with the capitalization of names.

MY_BONDING_DISP_INPUT_FILENAME = 'bonding_disp.txt'


def M3000_init_model_3_restart_from_model_2():
    model = mdb.Model(name='Model-3', objectToCopy=mdb.models['Model-2'])
    model.setValues(restartJob='Job-2', restartStep='Step-1')


def M3010_create_model_3_step_2():
    model = mdb.models['Model-3']

    model.StaticStep(
        name='Step-2',
        previous='Step-1',
        initialInc=1.0,
        maxNumInc=9999,
        minInc=1e-5,
        maxInc=1.0,
        nlgeom=ON,
    )
    # Restart is disabled for this step because it is unnecessary.
    model.steps['Step-2'].Restart(
        frequency=0,
        numberIntervals=0,
        overlay=ON,
        timeMarks=OFF,
    )


def M3020_modify_model_3_bonding_bc_at_step_2():
    model = mdb.models['Model-3']
    assembly = model.rootAssembly

    loaded_data = np.loadtxt('bonding_disp.txt', ndmin=2)
    for bc_name in model.boundaryConditions.keys():
        if bc_name.startswith('BONDING-'):
            bonding_label = int(bc_name.split('-')[1])
            u1, u2, u3, ur1, ur2, ur3 = loaded_data[bonding_label-1]
            if 'ROTABLE' in bc_name:
                model.boundaryConditions[bc_name].setValuesInStep(
                    stepName='Step-2',
                    u1=u1, u2=u2, u3=u3, ur1=ur1, ur2=ur2, ur3=UNSET,
                )
            else:
                model.boundaryConditions[bc_name].setValuesInStep(
                    stepName='Step-2',
                    u1=u1, u2=u2, u3=u3, ur1=ur1, ur2=ur2, ur3=ur3,
                )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(step='Step-2')
    viewport.assemblyDisplay.setValues(bcs=ON, constraints=ON)
    viewport.view.fitView()


def M3030_create_restart_job_3():
    job = mdb.Job(name='Job-3', model='Model-3', type=RESTART)
    job.writeInput(consistencyChecking=OFF)


# If the file is used as a script.
if __name__ == '__main__':
    M3000_init_model_3_restart_from_model_2()
    M3010_create_model_3_step_2()
    M3020_modify_model_3_bonding_bc_at_step_2()
    M3030_create_restart_job_3()

# If the file is named 'abaqusMacro.py' and used as Abaqus macro.
elif __name__ == '_currentMacros':
    print(r"""
 ____________________________________________________________________________ 
|                                                                            |
|     ___           __    ___           ___                     __   __      |
|    / _ )__ ______/ /__ / (_)__  ___ _/ _ | ___ ___ ___ __ _  / /  / /_ __  |
|   / _  / // / __/  '_// / / _ \/ _ `/ __ |(_-<(_-</ -_)  ' \/ _ \/ / // /  |
|  /____/\_,_/\__/_/\_\/_/_/_//_/\_, /_/ |_/___/___/\__/_/_/_/_.__/_/\_, /   |
|                               /___/                               /___/    |
|                                                                            |
|____________________________________________________________________________|
""".lstrip('\n')
    )
