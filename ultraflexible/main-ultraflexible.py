# Copyright (C) 2021-2025, Hu Xiaonan
# License: MIT License

from abaqus import *
from abaqusConstants import *
import interaction
import mesh
import step
from dxf2abq import importdxf

import numpy as np

# All my global constants start with the prefix `MY_` to prevent name
# duplication with Abaqus.

# Abaqus tends to convert some names to uppercase when storing them to ODB, so
# be careful with the capitalization of names.

MY_DXF_NAME = 'precursor'  # Do NOT end with `.dxf`.
MY_MATERIAL_DENSITY = 1e-9
MY_MATERIAL_EMOD = 2.5e3
MY_MATERIAL_POISON = 0.35
MY_SHELL_THICKNESS = 5e-3
MY_MESH_SEED_SIZE = 0.02
MY_MESH_SEED_DEVIATION_FACTOR = 0.1  # Set to `None` to disable.
MY_MESH_SEED_MIN_SIZE_FACTOR = 0.1
MY_VIRTUAL_TOPOLOGY_SHORT_EDGE_THRESHOLD = 0.01  # Set to `None` to disable.
MY_BONDING_INPUT_FILENAME = 'bonding.txt'
MY_MASS_SCALING = 1e4  # Set to `None` to disable.
MY_RAYLEIGH_DAMPING_COEFFICIENTS = (1e2, 0.0, 0.0, 0.0)  # (alpha, beta, composite, structural)
MY_SUBSTRATE_SHRINKING_CENTER = [0, 0]
MY_SUBSTRATE_SHRINKAGE = 0.5
MY_FLOOR_SIZE = 2.0
MY_ENABLE_RESTART = False
MY_FOUTPUT_VARIABLES = ['S', 'U']
MY_FOUTPUT_NUM = 50


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
    material.Density(table=[[MY_MATERIAL_DENSITY]])
    material.Elastic(table=[[MY_MATERIAL_EMOD, MY_MATERIAL_POISON]])
    material.Damping(
        alpha=MY_RAYLEIGH_DAMPING_COEFFICIENTS[0],
        beta=MY_RAYLEIGH_DAMPING_COEFFICIENTS[1],
        composite=MY_RAYLEIGH_DAMPING_COEFFICIENTS[2],
        structural=MY_RAYLEIGH_DAMPING_COEFFICIENTS[3],
    )
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
        elemLibrary=EXPLICIT,
    )
    elem_type_2 = mesh.ElemType(
        elemCode=S3,
        elemLibrary=EXPLICIT,
    )
    assembly.setElementType(
        regions=[instance.faces],
        elemTypes=[elem_type_1, elem_type_2],
    )

    if MY_VIRTUAL_TOPOLOGY_SHORT_EDGE_THRESHOLD is not None:
        try:
            assembly.createVirtualTopology(
                regions=[instance],
                mergeShortEdges=True,
                shortEdgeThreshold=MY_VIRTUAL_TOPOLOGY_SHORT_EDGE_THRESHOLD,
            )
        except AbaqusException:
            pass

    assembly.generateMesh(regions=[instance])

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(mesh=ON)
    viewport.view.fitView()


def M1060_create_step():
    model = mdb.models['Model-1']
    model.ExplicitDynamicsStep(name='Step-1', previous='Initial')
    if MY_MASS_SCALING is not None:
        model.steps['Step-1'].setValues(
            massScaling=(
                (SEMI_AUTOMATIC, MODEL, AT_BEGINNING, MY_MASS_SCALING, 0.0, None, 0, 0, 0.0, 0.0, 0, None),
            )
        )
    for k in model.fieldOutputRequests.keys():
        del model.fieldOutputRequests[k]
    for k in model.historyOutputRequests.keys():
        del model.historyOutputRequests[k]
    field_output_request = model.FieldOutputRequest(
        name='F-Output-1',
        createStepName='Step-1',
        variables=MY_FOUTPUT_VARIABLES,
        numIntervals=MY_FOUTPUT_NUM,
    )


def M1070_create_bonding_bc():
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

    model.TabularAmplitude(
        name='LINEAR',
        timeSpan=STEP,
        smooth=SOLVER_DEFAULT,
        data=[[0.0, 0.0], [1.0, 1.0]],
    )

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
            bonding_nodes = nodes.getByBoundingCylinder([xc, yc, -EPS], [xc, yc, +EPS],r+EPS)
        elif values[0].upper() == 'RECT':
            try:
                x1, y1, x2, y2, rotatable = _parse_rectangular_bonding(values)
            except (AssertionError, ValueError):
                raise ValueError('Invalid bonding format at line {}: {}'.format(line_num+1, line))
            bonding_nodes = nodes.getByBoundingBox(x1-EPS, y1-EPS, -EPS, x2+EPS, y2+EPS, +EPS)
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
        coords_2d = np.asarray([xc, yc])
        disp = -MY_SUBSTRATE_SHRINKAGE*(coords_2d-MY_SUBSTRATE_SHRINKING_CENTER)
        if rotatable:
            model.DisplacementBC(
                name='BONDING-{}-ROTATABLE'.format(counter+1),
                createStepName='Step-1',
                region=refpoint_set,
                u1=disp[0], u2=disp[1], u3=0, ur1=0, ur2=0, ur3=UNSET,
                amplitude='LINEAR',
            )
        else:
            model.DisplacementBC(
                name='BONDING-{}'.format(counter+1),
                createStepName='Step-1',
                region=refpoint_set,
                u1=disp[0], u2=disp[1], u3=0, ur1=0, ur2=0, ur3=0,
                amplitude='LINEAR',
            )
        counter += 1

    # Create a set of non-bonding nodes for potential later use.
    assembly.Set(
        name='NODES-NONBONDING',
        nodes=nodes.sequenceFromLabels(list(nonbonding_node_labels)),
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(step='Step-1')
    viewport.assemblyDisplay.setValues(bcs=ON, constraints=ON)
    viewport.view.fitView()


def M1080_create_floor():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly

    sketch = model.ConstrainedSketch(name='__profile__', sheetSize=200.0)
    sketch.Line(point1=(0.0, -MY_FLOOR_SIZE/2.0), point2=(0.0, MY_FLOOR_SIZE/2.0))
    part = model.Part(name='FLOOR', dimensionality=THREE_D, type=ANALYTIC_RIGID_SURFACE)
    part.AnalyticRigidSurfExtrude(sketch=sketch, depth=MY_FLOOR_SIZE)
    del model.sketches['__profile__']
    datum_point = part.DatumPointByMidPoint(
        point1=part.InterestingPoint(edge=part.edges[0], rule=MIDDLE), 
        point2=part.InterestingPoint(edge=part.edges[2], rule=MIDDLE),
    )
    part.ReferencePoint(point=part.datums[datum_point.id])
    instance = assembly.Instance(name='FLOOR', part=part, dependent=OFF)
    assembly.rotate(
        instanceList=['FLOOR'],
        axisPoint=(0.0, 0.0, 0.0),
        axisDirection=(0.0, 1.0, 0.0),
        angle=90.0,
    )
    assembly.Surface(side1Faces=instance.faces, name='FLOOR-TOP')

    rp_set = assembly.Set(
        name='RP-FLOOR',
        referencePoints=[instance.referencePoints.findAt((0.0, 0.0, 0.0))],
    )
    model.DisplacementBC(
        name='FIXED-FLOOR',
        createStepName='Initial', 
        region=rp_set,
        u1=0, u2=0, u3=0, ur1=0, ur2=0, ur3=0,
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(step='Initial')
    viewport.assemblyDisplay.setValues(bcs=ON, constraints=ON)
    viewport.view.fitView()


def M1090_create_general_contact():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly

    property = model.ContactProperty('IntProp-1')
    property.TangentialBehavior(formulation=FRICTIONLESS)
    property.NormalBehavior(pressureOverclosure=HARD)

    interaction = model.ContactExp(name='Int-1', createStepName='Initial')
    interaction.includedPairs.setValuesInStep(stepName='Initial', useAllstar=ON)
    interaction.contactPropertyAssignments.appendInStep(
        stepName='Initial',
        assignments=((GLOBAL, SELF, 'IntProp-1'), ),
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(interactions=ON)
    viewport.view.fitView()


def M1100_create_job_1_inp():
    job = mdb.Job(
        name='Job-1',
        model='Model-1',
        explicitPrecision=DOUBLE_PLUS_PACK,
    )
    job.writeInput(consistencyChecking=OFF)


# If the file is used as a script.
if __name__ == '__main__':
    M1000_new_model_1()
    M1010_import_sketch_from_dxf()
    M1020_create_part_from_sketch()
    M1030_create_material_and_section()
    M1040_create_instance()
    M1050_create_mesh()
    M1060_create_step()
    M1070_create_bonding_bc()
    M1080_create_floor()
    M1090_create_general_contact()
    M1100_create_job_1_inp()

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
