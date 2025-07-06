# Copyright (C) 2021-2025, Hu Xiaonan
# License: MIT License

# This script has been tested with:
#
# - Abaqus 2021 (recommended)
# - Abaqus 6.14 (legacy, some output variables not available)
#
# Compatibility with other Abaqus versions is not guaranteed.

from abaqus import *
from abaqusConstants import *
import interaction

# All my global constants start with the prefix `MY_` to prevent name
# duplication with Abaqus.

# Abaqus tends to convert some names to uppercase when storing them to ODB, so
# be careful with the capitalization of names.

MY_DAMAGE_MAX_CONTACT_STRESS = (2e-1, 2e1, 2e1)  # (Normal, Shear-1, Shear-2).
MY_DAMAGE_SEPARATION_AT_COMPLETE_FAILURE = 1e-6

MY_STEP_3_FOUTPUT_VARIABLES = ['U', 'S', 'LE', 'CSTRESS', 'CDISP', 'CSLIPR', 'CTANDIR', 'CFORCE', 'CTHICK', 'FSLIPR', 'FSLIP', 'CSTATUS', 'CSTRESS', 'CSDMG', 'CSMAXSCRT']
# Note: Abaqus 6.14 does not support the outputs 'CSTATUS', 'CDISP', 'CTANDIR', 'CSLIPR'.


def M1000_add_cohesive():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly

    cohesive_contact = model.ContactProperty('COHESIVE')
    cohesive_contact.NormalBehavior(pressureOverclosure=HARD, allowSeparation=ON)
    cohesive_contact.TangentialBehavior(formulation=FRICTIONLESS)
    cohesive_contact.CohesiveBehavior(
        repeatedContacts=ON,
        eligibility=ALL_NODES,
    )
    cohesive_contact.Damage(
        criterion=MAX_STRESS,
        initTable=[MY_DAMAGE_MAX_CONTACT_STRESS],
        useEvolution=ON,
        evolutionType=DISPLACEMENT,
        evolTable=[[MY_DAMAGE_SEPARATION_AT_COMPLETE_FAILURE]],
    )

    del model.interactions['Int-1']
    inter = model.ContactExp(name='Int-1', createStepName='Step-3')
    inter.includedPairs.setValuesInStep(stepName='Step-3', useAllstar=ON)
    inter.contactPropertyAssignments.appendInStep(
        stepName='Step-3',
        assignments=[
            (GLOBAL, SELF, 'NONBONDING'),
            (assembly.surfaces['SUBSTRATE-TOP-BONDING'], assembly.surfaces['STRUCTURE-BOTTOM-BONDING'], 'BONDING'),
            (assembly.surfaces['SUBSTRATE-TOP-NONBONDING'], assembly.surfaces['STRUCTURE-BOTTOM-NONBONDING'], 'COHESIVE'),
        ],
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(interactions=ON)
    viewport.view.fitView()


def M1010_modify_step_3():
    model = mdb.models['Model-1']

    model.fieldOutputRequests['F-Output-1'].setValuesInStep(
        stepName='Step-3',
        variables=MY_STEP_3_FOUTPUT_VARIABLES,
    )



# If the file is used as a script.
if __name__ == '__main__':
    M1000_add_cohesive()
    M1010_modify_step_3()

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
