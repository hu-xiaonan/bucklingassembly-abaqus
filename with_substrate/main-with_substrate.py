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

import numpy as np

# All my global constants start with the prefix `MY_` to prevent name
# duplication with Abaqus.

# Abaqus tends to convert some names to uppercase when storing them to ODB, so
# be careful with the capitalization of names.

MY_STRUCTURE_DXF_NAME = 'precursor'  # Do NOT end with `.dxf`.
MY_STRUCTURE_MATERIAL_EMOD = 2.5e3
MY_STRUCTURE_MATERIAL_POISSON = 0.35
MY_STRUCTURE_SHELL_THICKNESS = 10e-3
MY_STRUCTURE_MESH_SEED_SIZE = 0.02
MY_STRUCTURE_MESH_SEED_DEVIATION_FACTOR = 0.1  # Set to `None` to disable.
MY_STRUCTURE_MESH_SEED_MIN_SIZE_FACTOR = 0.1

MY_SUBSTRATE_X_LEN = 3.0
MY_SUBSTRATE_Y_LEN = 3.0
MY_SUBSTRATE_MATERIAL_EMOD = 1e0
MY_SUBSTRATE_SHELL_THICKNESS = 0.5
MY_SUBSTRATE_MESH_SEED_SIZE = 0.04
MY_SUBSTRATE_MESH_SEED_DEVIATION_FACTOR = 0.1  # Set to `None` to disable.
MY_SUBSTRATE_MESH_SEED_MIN_SIZE_FACTOR = 0.1

MY_SUBSTRATE_PRESTRAIN = 0.5
MY_BONDING_INPUT_FILENAME = 'bonding.txt'
MY_INITIAL_SEPARATION = 0.1

MY_FOUTPUT_VARIABLES = ['U', 'S', 'LE', 'CSTATUS']
MY_STEP_1_FOUTPUT_NUM = 10  # Set to `None` to disable.
MY_STEP_3_FOUTPUT_NUM = 10  # Set to `None` to disable.
MY_ENABLE_RESTART = False


def M1000_new_model_1():
    model = mdb.Model(name='Model-1', modelType=STANDARD_EXPLICIT)

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=None)


def M1010_import_structure_sketch_from_dxf():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly
    # The abaqus function `importdxf` will import the sketch into the model
    # currently displayed on the viewport, so it is necessary to switch the
    # viewport before importing the sketch to the target model.
    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    if model.sketches.has_key(MY_STRUCTURE_DXF_NAME):
        del model.sketches[MY_STRUCTURE_DXF_NAME]
    importdxf(fileName=MY_STRUCTURE_DXF_NAME+'.dxf')


def M1020_create_structure_part_from_sketch():
    model = mdb.models['Model-1']
    part = model.Part(name='STRUCTURE', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseShell(sketch=model.sketches[MY_STRUCTURE_DXF_NAME])

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=part)
    viewport.view.fitView()


def M1030_create_structure_material_and_section():
    model = mdb.models['Model-1']
    part = model.parts['STRUCTURE']
    material = model.Material(name='Material-1')
    material.Elastic(table=[[MY_STRUCTURE_MATERIAL_EMOD, MY_STRUCTURE_MATERIAL_POISSON]])
    model.HomogeneousShellSection(
        name='Section-1',
        material='Material-1',
        thickness=MY_STRUCTURE_SHELL_THICKNESS,
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


def M1040_create_structure_instance():
    model = mdb.models['Model-1']
    part = model.parts['STRUCTURE']
    assembly = model.rootAssembly
    assembly.Instance(name='STRUCTURE', part=part, dependent=OFF)
    assembly.translate(
        instanceList=['STRUCTURE'],
        vector=(0.0, 0.0, MY_INITIAL_SEPARATION),
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.view.fitView()


def M1050_create_structure_mesh():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly
    instance = assembly.instances['STRUCTURE']

    assembly.seedPartInstance(
        regions=[instance],
        size=MY_STRUCTURE_MESH_SEED_SIZE,
        deviationFactor=MY_STRUCTURE_MESH_SEED_DEVIATION_FACTOR,
        minSizeFactor=MY_STRUCTURE_MESH_SEED_MIN_SIZE_FACTOR,
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


def M1060_create_substrate_part():
    model = mdb.models['Model-1']

    sketch = model.ConstrainedSketch(name='__profile__', sheetSize=200.0)
    sketch.rectangle(
        point1=(-MY_SUBSTRATE_X_LEN/2.0, -MY_SUBSTRATE_Y_LEN/2.0),
        point2=(+MY_SUBSTRATE_X_LEN/2.0, +MY_SUBSTRATE_Y_LEN/2.0),
    )
    part = model.Part(name='SUBSTRATE', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=MY_SUBSTRATE_SHELL_THICKNESS)
    del model.sketches['__profile__']

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=part)
    viewport.view.fitView()


def M1070_create_substrate_material_and_section():
    def get_neohooke_coeff(E, nu):
        C10 = E/(4.0*(1.0+nu))
        D = 6.0*(1.0-2.0*nu)/E
        return (C10, D)

    model = mdb.models['Model-1']
    part = model.parts['SUBSTRATE']
    material = model.Material(name='Material-2')
    material.Hyperelastic(
        materialType=ISOTROPIC,
        testData=OFF,
        type=NEO_HOOKE, 
        volumetricResponse=VOLUMETRIC_DATA,
        table=[get_neohooke_coeff(MY_SUBSTRATE_MATERIAL_EMOD, 0.49)],
    )
    model.HomogeneousSolidSection(name='Section-2', material='Material-2')
    del part.sectionAssignments[:]
    part_cell_set = part.Set(cells=part.cells, name='CELLS-ALL')
    part.SectionAssignment(region=part_cell_set, sectionName='Section-2')

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=part)
    viewport.partDisplay.setValues(sectionAssignments=ON)
    viewport.view.fitView()


def M1080_create_substrate_instance():
    model = mdb.models['Model-1']
    part = model.parts['SUBSTRATE']
    assembly = model.rootAssembly
    assembly.Instance(name='SUBSTRATE', part=part, dependent=OFF)
    assembly.translate(
        instanceList=['SUBSTRATE'],
        vector=(0.0, 0.0, -MY_SUBSTRATE_SHELL_THICKNESS),
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.view.fitView()


def M1090_create_substrate_mesh():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly
    instance = assembly.instances['SUBSTRATE']

    assembly.seedPartInstance(
        regions=[instance],
        size=MY_SUBSTRATE_MESH_SEED_SIZE,
        deviationFactor=MY_SUBSTRATE_MESH_SEED_DEVIATION_FACTOR,
        minSizeFactor=MY_SUBSTRATE_MESH_SEED_MIN_SIZE_FACTOR,
    )
    elem_type_1 = mesh.ElemType(elemCode=C3D8RH, elemLibrary=STANDARD)
    elem_type_2 = mesh.ElemType(elemCode=C3D6H, elemLibrary=STANDARD)
    elem_type_3 = mesh.ElemType(elemCode=C3D4H, elemLibrary=STANDARD)
    assembly.setElementType(
        regions=[instance.cells],
        elemTypes=[elem_type_1, elem_type_2, elem_type_3],
    )
    assembly.generateMesh(regions=[instance])

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(mesh=ON)
    viewport.view.fitView()


def M1100_create_step():
    model = mdb.models['Model-1']

    # Step-1: Apply prestrain to the substrate.
    model.StaticStep(
        name='Step-1',
        previous='Initial',
        initialInc=1.0,
        maxNumInc=9999,
        minInc=1e-5,
        maxInc=1.0,
        nlgeom=ON,
    )
    # Step-2: Bond the structure onto the prestrained substrate.
    model.StaticStep(
        name='Step-2',
        previous='Step-1',
        nlgeom=ON,
    )
    # Step-3: Release the prestrain, allowing the structure to assemble.
    model.StaticStep(
        name='Step-3',
        previous='Step-2',
        initialInc=1.0,
        maxNumInc=9999,
        minInc=1e-15,
        maxInc=1.0,
        nlgeom=ON,
    )
    if MY_ENABLE_RESTART:
        model.steps['Step-3'].Restart(
            frequency=1,
            numberIntervals=0,
            overlay=ON,
            timeMarks=OFF,
        )
    field_output_request = model.FieldOutputRequest(
        name='F-Output-1',
        createStepName='Step-1',
        variables=MY_FOUTPUT_VARIABLES,
    )
    if MY_STEP_1_FOUTPUT_NUM is None:
        field_output_request.setValuesInStep(stepName='Step-1', frequency=1)
    else:
        field_output_request.setValuesInStep(stepName='Step-1', numIntervals=MY_STEP_1_FOUTPUT_NUM)
    field_output_request.setValuesInStep(stepName='Step-2', frequency=LAST_INCREMENT)
    if MY_STEP_3_FOUTPUT_NUM is None:
        field_output_request.setValuesInStep(stepName='Step-3', frequency=1)
    else:
        field_output_request.setValuesInStep(stepName='Step-3', numIntervals=MY_STEP_3_FOUTPUT_NUM)
    model.HistoryOutputRequest(
        name='H-Output-1',
        createStepName='Step-1',
        variables=PRESELECT,
        frequency=1,
    )


def M1110_create_contact():
    def _parse_circular_bonding(line_values):
        xc = float(line_values[1])
        yc = float(line_values[2])
        r = float(line_values[3])
        return xc, yc, r

    def _parse_rectangular_bonding(line_values):
        x1 = float(line_values[1])
        y1 = float(line_values[2])
        x2 = float(line_values[3])
        y2 = float(line_values[4])
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        return x1, y1, x2, y2

    model = mdb.models['Model-1']
    assembly = model.rootAssembly

    EPS = 1e-6

    structure_nodes = assembly.instances['STRUCTURE'].nodes
    structure_elements = assembly.instances['STRUCTURE'].elements
    structure_bottom_surface = assembly.Surface(name='STRUCTURE-BOTTOM', side2Elements=structure_elements)

    substrate_nodes = assembly.instances['SUBSTRATE'].nodes
    substrate_elements = assembly.instances['SUBSTRATE'].elements
    substrate_top_nodes = substrate_nodes.getByBoundingBox(zMin=-EPS)
    substrate_top_elements = substrate_elements.sequenceFromLabels(
        [elem.label for node in substrate_top_nodes for elem in node.getElements()]
    )

    # Select nodes and elements in the bonding regions of the structure and
    # substrate based on the data file `MY_BONDING_INPUT_FILENAME`.
    selected_structure_bonding_nodes = structure_nodes[0:0]
    selected_structure_bonding_elements = structure_elements[0:0]
    selected_substrate_nodes = substrate_nodes[0:0]
    with open(MY_BONDING_INPUT_FILENAME, 'r') as f:
        bonding_txt_lines = f.readlines()
    for line_num, line in enumerate(bonding_txt_lines):
        values = line.split()
        if len(values) == 0 or values[0].startswith('#'):
            continue
        if values[0].upper() == 'CIRCLE':
            try:
                xc, yc, r = _parse_circular_bonding(values)
            except (AssertionError, ValueError):
                raise ValueError('Invalid bonding format at line {}: {}'.format(line_num+1, line))
            selected_structure_bonding_nodes += structure_nodes.getByBoundingCylinder(
                center1=(xc, yc, MY_INITIAL_SEPARATION-EPS),
                center2=(xc, yc, MY_INITIAL_SEPARATION+EPS),
                radius=r+EPS,
            )
            # The following code only selects the elements that are completely
            # inside the cylinder (i.e., not touching the cylinder boundary).
            selected_structure_bonding_elements += structure_elements.getByBoundingCylinder(
                center1=(xc, yc, MY_INITIAL_SEPARATION-EPS),
                center2=(xc, yc, MY_INITIAL_SEPARATION+EPS),
                radius=r+EPS,
            )
            # To ensure the substrate bonding regions fully cover the structure
            # bonding regions, we select all elements that intersect the
            # cylinder. Since Abaqus lacks a direct API for this, we use a
            # workaround: first select the nodes within the bounding cylinder,
            # then later select all elements that contain these nodes (outside
            # this loop).
            xc_shrunk = xc/(1+MY_SUBSTRATE_PRESTRAIN)
            yc_shrunk = yc/(1+MY_SUBSTRATE_PRESTRAIN)
            selected_substrate_nodes += substrate_nodes.getByBoundingCylinder(
                center1=(xc_shrunk, yc_shrunk, -EPS),
                center2=(xc_shrunk, yc_shrunk, +EPS),
                radius=r+EPS,
            )
        elif values[0].upper() == 'RECT':
            try:
                x1, y1, x2, y2 = _parse_rectangular_bonding(values)
            except (AssertionError, ValueError):
                raise ValueError('Invalid bonding format at line {}: {}'.format(line_num+1, line))
            selected_structure_bonding_nodes += structure_nodes.getByBoundingBox(
                x1-EPS, y1-EPS, MY_INITIAL_SEPARATION-EPS,
                x2+EPS, y2+EPS, MY_INITIAL_SEPARATION+EPS,
            )
            selected_structure_bonding_elements += structure_elements.getByBoundingBox(
                x1-EPS, y1-EPS, MY_INITIAL_SEPARATION-EPS,
                x2+EPS, y2+EPS, MY_INITIAL_SEPARATION+EPS,
            )
            # As explained above, we first select substrate nodes for later
            # element selection (outside this loop).
            x1_shrunk = x1/(1+MY_SUBSTRATE_PRESTRAIN)
            y1_shrunk = y1/(1+MY_SUBSTRATE_PRESTRAIN)
            x2_shrunk = x2/(1+MY_SUBSTRATE_PRESTRAIN)
            y2_shrunk = y2/(1+MY_SUBSTRATE_PRESTRAIN)
            selected_substrate_nodes += substrate_nodes.getByBoundingBox(
                x1_shrunk, y1_shrunk, -EPS,
                x2_shrunk, y2_shrunk, +EPS,
            )
        else:
            raise ValueError('Unknown bonding type: {}'.format(values[0]))

    # Select all substrate elements that contain any of the selected nodes.
    # This ensures the bonding region on the substrate covers all relevant
    # nodes on the structure.
    selected_substrate_bonding_elements = substrate_elements.sequenceFromLabels(
        [elem.label for node in selected_substrate_nodes for elem in node.getElements()]
    )

    # Create a pair of complementary surfaces which are the bonding and
    # non-bonding regions on the structure. These surfaces will be assigned
    # different contact properties.
    structure_bottom_bonding_surface = assembly.Surface(
        name='STRUCTURE-BOTTOM-BONDING',
        side2Elements=selected_structure_bonding_elements,
    )
    assembly.SurfaceByBoolean(
        name='STRUCTURE-BOTTOM-NONBONDING',
        operation=DIFFERENCE,
        surfaces=(structure_bottom_surface, structure_bottom_bonding_surface),
    )

    # Similarly, create a pair of complementary surfaces for the substrate.
    substrate_top_surface = assembly.Surface(
        name='SUBSTRATE-TOP',
        face3Elements=substrate_top_elements,
    )
    substrate_top_bonding_surface = assembly.Surface(
        name='SUBSTRATE-TOP-BONDING',
        face3Elements=selected_substrate_bonding_elements,
    )
    assembly.SurfaceByBoolean(
        name='SUBSTRATE-TOP-NONBONDING',
        operation=DIFFERENCE,
        surfaces=(substrate_top_surface, substrate_top_bonding_surface),
    )

    bonding_contact = model.ContactProperty('BONDING')
    bonding_contact.NormalBehavior(pressureOverclosure=HARD, allowSeparation=OFF)
    bonding_contact.TangentialBehavior(formulation=ROUGH)
    model.SurfaceToSurfaceContactStd(
        name='BONDING',
        createStepName='Step-3',
        master=assembly.surfaces['SUBSTRATE-TOP-BONDING'],
        slave=assembly.surfaces['STRUCTURE-BOTTOM-BONDING'],
        sliding=FINITE,
        thickness=ON,
        interactionProperty='BONDING',
    )

    nonbonding_contact = model.ContactProperty('NONBONDING')
    nonbonding_contact.NormalBehavior(pressureOverclosure=HARD, allowSeparation=ON)
    nonbonding_contact.TangentialBehavior(formulation=FRICTIONLESS)
    model.SurfaceToSurfaceContactStd(
        name='NONBONDING',
        createStepName='Step-3',
        master=assembly.surfaces['SUBSTRATE-TOP-NONBONDING'],
        slave=assembly.surfaces['STRUCTURE-BOTTOM-NONBONDING'],
        sliding=FINITE,
        thickness=ON,
        interactionProperty='NONBONDING',
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(interactions=ON)
    viewport.view.fitView()


def M1120_create_bonding_disp_bc():
    model = mdb.models['Model-1']
    assembly = model.rootAssembly

    EPS = 1e-6

    # Apply prestrain to the substrate in Step-1, and release it in Step-3.
    substrate_xneg_face_set = assembly.Set(
        name='FACES-SUBSTRATE-XNEG',
        faces=assembly.instances['SUBSTRATE'].faces.getByBoundingBox(
            -MY_SUBSTRATE_X_LEN/2.0-EPS, -MY_SUBSTRATE_Y_LEN/2.0-EPS, -MY_SUBSTRATE_SHELL_THICKNESS-EPS,
            -MY_SUBSTRATE_X_LEN/2.0+EPS, +MY_SUBSTRATE_Y_LEN/2.0+EPS, +EPS,
        ),
    )
    substrate_xpos_face_set = assembly.Set(
        name='FACES-SUBSTRATE-XPOS',
        faces=assembly.instances['SUBSTRATE'].faces.getByBoundingBox(
            +MY_SUBSTRATE_X_LEN/2.0-EPS, -MY_SUBSTRATE_Y_LEN/2.0-EPS, -MY_SUBSTRATE_SHELL_THICKNESS-EPS,
            +MY_SUBSTRATE_X_LEN/2.0+EPS, +MY_SUBSTRATE_Y_LEN/2.0+EPS, +EPS,
        ),
    )
    substrate_yneg_face_set = assembly.Set(
        name='FACES-SUBSTRATE-YNEG',
        faces=assembly.instances['SUBSTRATE'].faces.getByBoundingBox(
            -MY_SUBSTRATE_X_LEN/2.0-EPS, -MY_SUBSTRATE_Y_LEN/2.0-EPS, -MY_SUBSTRATE_SHELL_THICKNESS-EPS,
            +MY_SUBSTRATE_X_LEN/2.0+EPS, -MY_SUBSTRATE_Y_LEN/2.0+EPS, +EPS,
        ),
    )
    substrate_ypos_face_set = assembly.Set(
        name='FACES-SUBSTRATE-YPOS',
        faces=assembly.instances['SUBSTRATE'].faces.getByBoundingBox(
            -MY_SUBSTRATE_X_LEN/2.0-EPS, +MY_SUBSTRATE_Y_LEN/2.0-EPS, -MY_SUBSTRATE_SHELL_THICKNESS-EPS,
            +MY_SUBSTRATE_X_LEN/2.0+EPS, +MY_SUBSTRATE_Y_LEN/2.0+EPS, +EPS,
        ),
    )
    substrate_xneg_disp_bc = model.DisplacementBC(
        name='SUBSTRATE-XNEG',
        createStepName='Step-1',
        region=substrate_xneg_face_set,
        u1=-MY_SUBSTRATE_PRESTRAIN*MY_SUBSTRATE_X_LEN/2.0,
    )
    substrate_xpos_disp_bc = model.DisplacementBC(
        name='SUBSTRATE-XPOS',
        createStepName='Step-1',
        region=substrate_xpos_face_set,
        u1=+MY_SUBSTRATE_PRESTRAIN*MY_SUBSTRATE_X_LEN/2.0,
    )
    substrate_yneg_disp_bc = model.DisplacementBC(
        name='SUBSTRATE-YNEG',
        createStepName='Step-1',
        region=substrate_yneg_face_set,
        u2=-MY_SUBSTRATE_PRESTRAIN*MY_SUBSTRATE_Y_LEN/2.0,
    )
    substrate_ypos_disp_bc = model.DisplacementBC(
        name='SUBSTRATE-YPOS',
        createStepName='Step-1',
        region=substrate_ypos_face_set,
        u2=+MY_SUBSTRATE_PRESTRAIN*MY_SUBSTRATE_Y_LEN/2.0,
    )
    substrate_xneg_disp_bc.setValuesInStep(stepName='Step-3', u1=0)
    substrate_xpos_disp_bc.setValuesInStep(stepName='Step-3', u1=0)
    substrate_yneg_disp_bc.setValuesInStep(stepName='Step-3', u2=0)
    substrate_ypos_disp_bc.setValuesInStep(stepName='Step-3', u2=0)

    # Apply boundary conditions to the structure:
    # - Step-1: Hold the structure in place.
    # - Step-2: Move the structure onto the substrate to establish contact.
    # - Step-3: Deactivate this BC after contact is established.
    assembly.Set(
        name='FACES-STRUCTURE',
        faces=assembly.instances['STRUCTURE'].faces,
    )
    model.DisplacementBC(
        name='STRUCTURE-BONDING',
        createStepName='Step-1',
        region=assembly.sets['FACES-STRUCTURE'],
        u1=0, u2=0, u3=0,
    )
    model.boundaryConditions['STRUCTURE-BONDING'].setValuesInStep(
        stepName='Step-2',
        u1=0, u2=0, u3=-MY_INITIAL_SEPARATION,
    )
    model.boundaryConditions['STRUCTURE-BONDING'].deactivate('Step-3')

    # The following boundary conditions serve two purposes:
    #
    # - Prevent rigid body motion of the model along the z-axis.
    #
    # - Hold the top surface of the substrate (u3=0) during the bonding step
    #   (Step-2), to ensure that all nodes in the structure bonding region
    #   achieve good contact with the substrate.
    #
    # Two complementary node sets are created on the top face of the substrate:
    # exterior nodes (on the edge of the top face) and interior nodes (not on
    # the edge). Different boundary conditions are applied:
    #
    # - Exterior nodes:
    #     Nodes on the edge of the top face, fixed in the z direction (u3=0) throughout all steps.
    #
    # - Interior nodes:
    #     Nodes not on the edge of the top face, fixed in the z direction (u3=0) in Step-1,
    #     and released in Step-3.
    substrate_top_node_set = assembly.Set(
        name='NODES-SUBSTRATE-TOP',
        nodes=assembly.instances['SUBSTRATE'].nodes.getByBoundingBox(zMin=-EPS),
    )
    substrate_top_interior_node_set = assembly.Set(
        name='NODES-SUBSTRATE-TOP-INTERIOR',
        nodes=assembly.instances['SUBSTRATE'].nodes.getByBoundingBox(
            -MY_SUBSTRATE_X_LEN/2.0+EPS, -MY_SUBSTRATE_Y_LEN/2.0+EPS, -EPS,
            +MY_SUBSTRATE_X_LEN/2.0-EPS, +MY_SUBSTRATE_Y_LEN/2.0-EPS, +EPS,
        ),
    )
    assembly.SetByBoolean(
        name='NODES-SUBSTRATE-TOP-EXTERIOR',
        operation=DIFFERENCE,
        sets=(substrate_top_node_set, substrate_top_interior_node_set),
    )
    model.DisplacementBC(
        name='SUBSTRATE-HOLD-EXTERIOR',
        createStepName='Step-1',
        region=assembly.sets['NODES-SUBSTRATE-TOP-EXTERIOR'],
        u3=0,
    )
    model.DisplacementBC(
        name='SUBSTRATE-HOLD-INTERIOR',
        createStepName='Step-1',
        region=assembly.sets['NODES-SUBSTRATE-TOP-INTERIOR'],
        u3=0,
    )
    model.boundaryConditions['SUBSTRATE-HOLD-INTERIOR'].deactivate('Step-3')

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(step='Step-1')
    viewport.assemblyDisplay.setValues(bcs=ON, constraints=ON)
    viewport.view.fitView()


def M1130_create_job_1_inp():
    job = mdb.Job(name='Job-1', model='Model-1')
    job.writeInput(consistencyChecking=OFF)


# If the file is used as a script.
if __name__ == '__main__':
    M1000_new_model_1()
    M1010_import_structure_sketch_from_dxf()
    M1020_create_structure_part_from_sketch()
    M1030_create_structure_material_and_section()
    M1040_create_structure_instance()
    M1050_create_structure_mesh()
    M1060_create_substrate_part()
    M1070_create_substrate_material_and_section()
    M1080_create_substrate_instance()
    M1090_create_substrate_mesh()
    M1100_create_step()
    M1110_create_contact()
    M1120_create_bonding_disp_bc()
    M1130_create_job_1_inp()

    mdb.saveAs('model.cae')

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
