# Copyright (C) 2021-2025, Hu Xiaonan
# License: MIT License

# This script has been tested with:
#
# - Abaqus 2021 (recommended)
# - Abaqus 6.14 (legacy)
#
# Compatibility with other Abaqus versions is not guaranteed.

from abaqus import *
from abaqusConstants import *
import interaction
import mesh
import step
from dxf2abq import importdxf

import re
import numpy as np

# All my global constants start with the prefix `MY_` to prevent name
# duplication with Abaqus.

# Abaqus tends to convert some names to uppercase when storing them to ODB, so
# be careful with the capitalization of names.

MY_DXF_NAME = 'precursor'  # Do NOT end with `.dxf`.
MY_MATERIAL_EMOD = 2.5e3
MY_MATERIAL_POISSON = 0.35
MY_SHELL_THICKNESS = 10e-3
MY_MESH_SEED_SIZE = 0.01
MY_MESH_SEED_DEVIATION_FACTOR = 0.1  # Set to `None` to disable.
MY_MESH_SEED_MIN_SIZE_FACTOR = 0.1
MY_BONDING_INPUT_FILENAME = 'bonding.txt'
MY_DISTURBANCE_INPUT_FILENAME = 'disturbance.txt'
MY_SUBSTRATE_SHRINKING_CENTER = [0, 0]
MY_SUBSTRATE_SHRINKAGE = 0.3
MY_DISTURBANCE_SCALE_FACTOR = 1.0  # SCALE_FACTOR := DISTURBANCE / SHELL_THICKNESS
MY_MODEL_2_ENABLE_RESTART = False
MY_MODEL_2_FOUTPUT_VARIABLES = ['S', 'U']
MY_MODEL_2_FOUTPUT_NUM = 10  # Set to `None` to disable.
MY_MODEL_2_GENERAL_CONTACT = False


def M1000_new_model_1():
    model = mdb.Model(name='Model-1', modelType=STANDARD_EXPLICIT)

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=None)


def M1010_import_sketch_from_dxf():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly
    # The abaqus function `importdxf` will import the sketch into the model
    # currently displayed on the viewport, so it is necessary to switch the
    # viewport before importing the sketch to the target model.
    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    if model.sketches.has_key(MY_DXF_NAME):
        del model.sketches[MY_DXF_NAME]
    importdxf(fileName=MY_DXF_NAME+'.dxf')


def M1020_create_part_from_sketch():
    model = mdb.models['Model-1']
    part = model.Part(name='STRUCTURE', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseShell(sketch=model.sketches[MY_DXF_NAME])

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=part)
    viewport.view.fitView()


def M1030_create_material_and_section():
    model = mdb.models['Model-1']
    part = model.parts['STRUCTURE']
    material = model.Material(name='Material-1')
    material.Elastic(table=[[MY_MATERIAL_EMOD, MY_MATERIAL_POISSON]])
    model.HomogeneousShellSection(
        name='Section-1',
        material='Material-1',
        thickness=MY_SHELL_THICKNESS,
    )
    del part.sectionAssignments[:]
    part_face_set = part.Set(faces=part.faces, name='FACES-ALL')
    part.SectionAssignment(
        region=part_face_set,
        sectionName='Section-1',
        offsetType=BOTTOM_SURFACE,
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=part)
    viewport.partDisplay.setValues(sectionAssignments=ON)
    viewport.view.fitView()


def M1040_create_instance():
    model = mdb.models['Model-1']
    part = model.parts['STRUCTURE']
    assembly = model.rootAssembly
    assembly.Instance(name='STRUCTURE', part=part, dependent=OFF)

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.view.fitView()


def M1050_create_mesh():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly
    instance = assembly.instances['STRUCTURE']

    assembly.seedPartInstance(
        regions=[instance],
        size=MY_MESH_SEED_SIZE,
        deviationFactor=MY_MESH_SEED_DEVIATION_FACTOR,
        minSizeFactor=MY_MESH_SEED_MIN_SIZE_FACTOR,
    )
    elem_type_1 = mesh.ElemType(
        elemCode=S4R,
        elemLibrary=STANDARD,
        secondOrderAccuracy=OFF,
        hourglassControl=DEFAULT,
    )
    elem_type_2 = mesh.ElemType(
        elemCode=S3,
        elemLibrary=STANDARD,
    )
    assembly.setElementType(
        regions=[instance.faces],
        elemTypes=[elem_type_1, elem_type_2],
    )
    assembly.generateMesh(regions=[instance])

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(mesh=ON)
    viewport.view.fitView()


def M1060_create_model_1_step():
    model = mdb.models['Model-1']
    model.StaticStep(name='Step-1', previous='Initial', nlgeom=OFF)
    field_output_request = model.FieldOutputRequest(
        name='F-Output-1',
        createStepName='Step-1',
        variables=['U'],
        frequency=1,
    )


def M1070_create_model_1_bonding_bc():
    def _parse_circular_bonding(line_values):
        xc = float(line_values[1])
        yc = float(line_values[2])
        r = float(line_values[3])
        rotatable = len(line_values) > 4 and line_values[4].upper() == 'ROTATABLE'
        return xc, yc, r, rotatable

    def _parse_rectangular_bonding(line_values):
        x1 = float(line_values[1])
        y1 = float(line_values[2])
        x2 = float(line_values[3])
        y2 = float(line_values[4])
        rotatable = len(line_values) > 5 and line_values[5].upper() == 'ROTATABLE'
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        return x1, y1, x2, y2, rotatable

    model = mdb.models['Model-1']
    assembly = model.rootAssembly
    instance = assembly.instances['STRUCTURE']
    nodes = instance.nodes

    EPS = 1e-6
    nonbonding_node_labels = set(n.label for n in nodes)
    counter = 0
    with open(MY_BONDING_INPUT_FILENAME, 'r') as f:
        bonding_txt_lines = f.readlines()
    for line_num, line in enumerate(bonding_txt_lines):
        values = line.split()
        if len(values) == 0 or values[0].startswith('#'):
            continue

        if values[0].upper() == 'CIRCLE':
            try:
                xc, yc, r, rotatable = _parse_circular_bonding(values)
            except (AssertionError, ValueError):
                raise ValueError('Invalid bonding format at line {}: {}'.format(line_num+1, line))
            bonding_nodes = nodes.getByBoundingCylinder([xc, yc, -EPS], [xc, yc, EPS], r+EPS)
        elif values[0].upper() == 'RECT':
            try:
                x1, y1, x2, y2, rotatable = _parse_rectangular_bonding(values)
            except (AssertionError, ValueError):
                raise ValueError('Invalid bonding format at line {}: {}'.format(line_num+1, line))
            bonding_nodes = nodes.getByBoundingBox(x1-EPS, y1-EPS, -EPS, x2+EPS, y2+EPS, EPS)
            xc = 0.5*(x1+x2)
            yc = 0.5*(y1+y2)
        else:
            raise ValueError('Unknown bonding type: {}'.format(values[0]))

        # Prevent applying redundant constraints to nodes that have already been constrained.
        bonding_nodes = bonding_nodes.sequenceFromLabels(
            list(set(n.label for n in bonding_nodes) & nonbonding_node_labels)
        )
        if len(bonding_nodes) == 0:
            raise ValueError(
                (
                    "No nodes found for bonding at line {}: {}\n"
                    "This may be due to an incorrect bonding definition, "
                    "or because all relevant nodes have already been "
                    "constrained by previous bonding definitions."
                ).format(line_num+1, line)
            )
        node_set = assembly.Set(
            name='NODES-BONDING-{}'.format(counter+1),
            nodes=bonding_nodes,
        )
        nonbonding_node_labels -= set(n.label for n in bonding_nodes)

        # Create a reference point at the center of the bonding area.
        rp_feature = assembly.ReferencePoint(point=[xc, yc, 0.0])
        # This is a workaround to rename the reference point feature.
        rp_feature_name = 'RP-BONDING-{}'.format(counter+1)
        if rp_feature.name != rp_feature_name:
            if assembly.features.has_key(rp_feature_name):
                del assembly.features[rp_feature_name]
            assembly.features.changeKey(fromName=rp_feature.name, toName=rp_feature_name)
        refpoint = assembly.referencePoints[rp_feature.id]
        refpoint_set = assembly.Set(
            name='RP-BONDING-{}'.format(counter+1),
            referencePoints=[refpoint],
        )

        # Create the bonding constraint.
        model.Coupling(
            name='COUPLING-BONDING-{}'.format(counter+1),
            controlPoint=refpoint_set,
            surface=node_set,
            influenceRadius=WHOLE_SURFACE,
            couplingType=KINEMATIC,
            u1=ON, u2=ON, u3=ON, ur1=ON, ur2=ON, ur3=ON,
        )
        if rotatable:
            model.DisplacementBC(
                name='BONDING-{}-ROTATABLE'.format(counter+1),
                createStepName='Step-1',
                region=refpoint_set,
                u1=0, u2=0, u3=0, ur1=0, ur2=0, ur3=UNSET,
            )
        else:
            model.DisplacementBC(
                name='BONDING-{}'.format(counter+1),
                createStepName='Step-1',
                region=refpoint_set,
                u1=0, u2=0, u3=0, ur1=0, ur2=0, ur3=0,
            )
        counter += 1

    # Create a set of non-bonding nodes for later use.
    assembly.Set(
        name='NODES-NONBONDING',
        nodes=nodes.sequenceFromLabels(list(nonbonding_node_labels)),
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(step='Step-1')
    viewport.assemblyDisplay.setValues(bcs=ON, constraints=ON)
    viewport.view.fitView()


def M1080_create_model_1_disturbance_bc():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly
    instance = assembly.instances['STRUCTURE']
    nodes = instance.nodes

    nonbonding_nodes = assembly.sets['NODES-NONBONDING'].nodes
    nonbonding_node_coords = np.asarray([n.coordinates for n in nonbonding_nodes])
    disturbed_node_labels = set()

    # Create the single-node sets on which the displacement BCs are applied.
    with open(MY_DISTURBANCE_INPUT_FILENAME) as f:
        input_lines = f.readlines()
    data_lines = [line for line in input_lines if not line.startswith('#')]
    counter = 0
    for x, y, deflection in np.loadtxt(data_lines, ndmin=2):
        # If Abaqus version > 6.14, we can use the method `getClosest`.
        #
        # closest_node = nonbonding_nodes.getClosest((x, y, 0.0))
        #
        # However, to be compatible with Abaqus 6.14, we have to find the
        # closest node manually.
        closest_node = nonbonding_nodes[
            np.argmin(np.hypot(nonbonding_node_coords[:, 0]-x, nonbonding_node_coords[:, 1]-y))
        ]
        if closest_node.label in disturbed_node_labels:
            print(
                (
                    'Skipping disturbance at ({}, {}) because node {} has '
                    'already been disturbed.'
                ).format(x, y, closest_node.label)
            )
            continue
        node_set = assembly.Set(
            name='NODE-DISTURBANCE-{}'.format(counter+1),
            nodes=nodes.sequenceFromLabels([closest_node.label]),
        )
        model.DisplacementBC(
            name='DISTURBANCE-{}'.format(counter+1),
            createStepName='Step-1',
            region=node_set,
            u3=deflection*MY_SHELL_THICKNESS,
        )
        disturbed_node_labels.add(closest_node.label)
        counter += 1

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(step='Step-1')
    viewport.assemblyDisplay.setValues(bcs=ON, constraints=ON)
    viewport.view.fitView()


def M1090_create_and_modify_job_1_inp():
    job = mdb.Job(name='Job-1', model='Model-1')
    job.writeInput(consistencyChecking=OFF)
    with open('Job-1.inp', 'r') as f:
        inp_text = f.read()
    NODE_FILE_BLOCK = '*Node file\nU\n'
    modified_inp_text, num = re.subn(
        r'(\*Step, name=Step-1.*?)(\*End step)',
        r'\1' + NODE_FILE_BLOCK + r'\2',
        inp_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if num != 1:
        raise RuntimeError('Failed to find the step definition in the input file.')
    with open('Job-1.inp', 'w') as f:
        f.write(modified_inp_text)
    job.setValues(description='Input file modified to include *Node file keyword.')


def M2000_clone_model_2_from_model_1():
    model = mdb.Model(name='Model-2', objectToCopy=mdb.models['Model-1'])
    assembly = model.rootAssembly

    del model.steps['Step-1']

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.view.fitView()


def M2010_create_model_2_step():
    model = mdb.models['Model-2']

    model.StaticStep(
        name='Step-1',
        previous='Initial',
        initialInc=1.0,
        maxNumInc=9999,
        minInc=1e-5,
        maxInc=1.0,
        nlgeom=ON,
    )
    if MY_MODEL_2_ENABLE_RESTART:
        model.steps['Step-1'].Restart(
            frequency=1,
            numberIntervals=0,
            overlay=ON,
            timeMarks=OFF,
        )
    field_output_request = model.FieldOutputRequest(
        name='F-Output-1',
        createStepName='Step-1',
        variables=MY_MODEL_2_FOUTPUT_VARIABLES,
        frequency=1,
    )
    if MY_MODEL_2_FOUTPUT_NUM is not None:
        field_output_request.setValues(numIntervals=MY_MODEL_2_FOUTPUT_NUM)
    model.HistoryOutputRequest(
        name='H-Output-1',
        createStepName='Step-1',
        variables=PRESELECT,
        frequency=1,
    )


def M2020_create_model_2_general_contact():
    model = mdb.models['Model-2']
    assembly = model.rootAssembly

    if MY_MODEL_2_GENERAL_CONTACT:
        property = model.ContactProperty('IntProp-1')
        property.TangentialBehavior(formulation=FRICTIONLESS)
        property.NormalBehavior(pressureOverclosure=HARD)

        interaction = model.ContactStd(name='Int-1', createStepName='Initial')
        interaction.includedPairs.setValuesInStep(stepName='Initial', useAllstar=ON)
        interaction.contactPropertyAssignments.appendInStep(
            stepName='Initial',
            assignments=((GLOBAL, SELF, 'IntProp-1'), ),
        )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(interactions=ON)
    viewport.view.fitView()


def M2030_create_model_2_bonding_bc():
    ref_model = mdb.models['Model-1']
    model = mdb.models['Model-2']
    assembly = model.rootAssembly

    # Copy and update the bonding constraints from Model-1.
    for bc_name in ref_model.boundaryConditions.keys():
        if bc_name.startswith('BONDING-'):
            refpoint_setname = ref_model.boundaryConditions[bc_name].region[0]
            refpoint_set = assembly.sets[refpoint_setname]
            feature = assembly.features[refpoint_setname]
            coords_2d = np.asarray([feature.xValue, feature.yValue])
            disp = -MY_SUBSTRATE_SHRINKAGE*(coords_2d-MY_SUBSTRATE_SHRINKING_CENTER)
            if '-ROTATABLE' in bc_name:
                model.DisplacementBC(
                    name=bc_name,
                    createStepName='Step-1',
                    region=refpoint_set,
                    u1=disp[0], u2=disp[1], u3=0, ur1=0, ur2=0, ur3=UNSET,
                )
            else:
                model.DisplacementBC(
                    name=bc_name,
                    createStepName='Step-1',
                    region=refpoint_set,
                    u1=disp[0], u2=disp[1], u3=0, ur1=0, ur2=0, ur3=0,
                )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(step='Step-1')
    viewport.assemblyDisplay.setValues(bcs=ON, constraints=ON)
    viewport.view.fitView()


def M2040_create_and_modify_job_2_inp():
    job = mdb.Job(name='Job-2', model='Model-2')
    job.writeInput(consistencyChecking=OFF)
    with open('Job-2.inp', 'r') as f:
        inp_text = f.read()
    IMPERFECTION_BLOCK = '*Imperfection, file=Job-1, step=1\n1, {}\n'.format(
        MY_DISTURBANCE_SCALE_FACTOR
    )
    modified_inp_text, num = re.subn(
        r'((?:\*\*[^\r\n]*?\n)*)(\*Step.*?\*End step)',
        IMPERFECTION_BLOCK + r'\1' + r'\2',
        inp_text,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if num != 1:
        raise RuntimeError('Failed to find the step definition in the input file.')
    with open('Job-2.inp', 'w') as f:
        f.write(modified_inp_text)
    job.setValues(description='Input file modified to include *Imperfection keyword.')


# If the file is used as a script.
if __name__ == '__main__':
    M1000_new_model_1()
    M1010_import_sketch_from_dxf()
    M1020_create_part_from_sketch()
    M1030_create_material_and_section()
    M1040_create_instance()
    M1050_create_mesh()
    M1060_create_model_1_step()
    M1070_create_model_1_bonding_bc()
    M1080_create_model_1_disturbance_bc()
    M1090_create_and_modify_job_1_inp()

    M2000_clone_model_2_from_model_1()
    M2010_create_model_2_step()
    M2020_create_model_2_general_contact()
    M2030_create_model_2_bonding_bc()
    M2040_create_and_modify_job_2_inp()

    mdb.saveAs(pathName='model')

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
