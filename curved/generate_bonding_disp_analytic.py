# Copyright (C) 2021-2025, Hu Xiaonan
# License: MIT License

import os
from pathlib import Path
import numpy as np

os.chdir(Path(__file__).parent.resolve())


def my_map(points_2d):
    # CHANGE THIS FUNCTION ON YOUR NEED.

    """
    Map multiple 2D points from the flat precursor to their final locations
    on the curved surface.

    Parameters
    ----------
    points_2d : numpy.ndarray, shape=(N, 2)
        Points on the planar precursor.

    Returns
    -------
    numpy.ndarray, shape=(N, 6)
        Mapped coordinates and rotation vectors for each point, where each row
        contains (x, y, z, urx, ury, urz) for the point.

    """
    # Calculate the point location after buckling assembly. The following two
    # parameters should be consistent with that in the `main-classical.py`
    # script.
    MY_SHRINKING_CENTER = np.asarray([0, 0])
    MY_SHRINKAGE = 0.3
    points_2d = np.asarray(points_2d)
    points_2d_shrunk = points_2d-MY_SHRINKAGE*(points_2d-MY_SHRINKING_CENTER)
    return map_cylinder(points_2d_shrunk, radius=2, orient_deg=90)


def map_cylinder_along_x(points_2d, radius):
    """
    Map 2D coordinates onto a cylinder surface (along the x-axis) with a
    specified radius.

    Parameters
    ----------
    points_2d : numpy.ndarray, shape=(N, 2)
        Points in the 2D plane.
    radius : float
        Cylinder radius.

    Returns
    -------
    points_3d : numpy.ndarray, shape=(N, 3)
        3D coordinates on the cylinder surface.
    rotvec : numpy.ndarray, shape=(N, 3)
        Rotation vector (axis-angle form).

    """
    points_2d = np.asarray(points_2d)
    u = points_2d[:, 0]
    v = points_2d[:, 1]
    angle = v/radius
    c = np.cos(angle)
    s = np.sin(angle)
    points_3d = np.column_stack([u, radius*s, -radius*(1-c)])
    rotvec = np.column_stack([-angle, np.zeros_like(angle), np.zeros_like(angle)])
    return points_3d, rotvec


def map_cylinder(points_2d, radius, orient_deg):
    """
    Map 2D coordinates onto the a cylinder surface with a given radius and
    orientation.

    Parameters
    ----------
    points_2d : numpy.ndarray, shape=(N, 2)
        Points in the 2D plane.
    radius : float
        Cylinder radius.
    orient_deg : float
        Angle between the cylinder's axis and the x-axis, in degrees, positive
        if counterclockwise when viewed from above.

    Returns
    -------
    points_3d : numpy.ndarray, shape=(3,)
        3D coordinates on the cylinder surface.
    rotvec : numpy.ndarray, shape=(3,)
        Rotation vector (axis-angle form).

    """
    orientation_rad = np.deg2rad(orient_deg)
    c = np.cos(orientation_rad)
    s = np.sin(orientation_rad)
    rot3d = np.asarray([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    points_2d = points_2d @ rot3d[:2, :2].T
    points_3d, rotvec = map_cylinder_along_x(points_2d, radius)
    points_3d = points_3d @ rot3d
    rotvec = rotvec @ rot3d
    return points_3d, rotvec


def map_sphere(points_2d, radius):
    """
    Map 2D coordinates onto a sphere surface with a given radius.

    Parameters
    ----------
    points_2d : numpy.ndarray, shape=(N, 2)
        Points in the 2D plane.
    radius : float
        Sphere radius.

    Returns
    -------
    points_3d : numpy.ndarray, shape=(3,)
        3D coordinates on the sphere surface.
    rotvec : numpy.ndarray, shape=(3,)
        Rotation vector (axis-angle form).

    """
    u = points_2d[:, 0]
    v = points_2d[:, 1]
    rho = np.hypot(u, v)
    phi = np.arctan2(v, u)
    cos_phi = np.cos(phi)
    sin_phi = np.sin(phi)
    # theta is the angle from the z-axis (colatitude).
    theta = rho/radius
    cos_theta = np.cos(theta)
    sin_theta = np.sin(theta)
    points_3d = radius*np.column_stack([sin_theta*cos_phi, sin_theta*sin_phi, -(1.0-cos_theta)])
    rotvec = np.column_stack([-sin_phi, cos_phi, np.zeros_like(phi)])*theta[:, np.newaxis]
    return points_3d, rotvec


def load_bonding_points_from_file():
    """
    Load the center coordinates of the bonding regions defined in `bonding.txt`.

    Returns
    -------
    points : numpy.ndarray, shape=(N, 2)
        Bonding points (xc, yc) coordinates.

    """
    points = []
    with open('bonding.txt', 'r') as f:
        bonding_txt_lines = f.readlines()
    for line in bonding_txt_lines:
        values = line.split()
        if len(values) == 0 or values[0].startswith('#'):
            continue
        if values[0].upper() == 'CIRCLE':
            xc = float(values[1])
            yc = float(values[2])
        elif values[0].upper() == 'RECT':
            x1 = float(values[1])
            y1 = float(values[2])
            x2 = float(values[3])
            y2 = float(values[4])
            xc = 0.5 * (x1 + x2)
            yc = 0.5 * (y1 + y2)
        else:
            raise ValueError('Unknown bonding type: {}'.format(values[0]))
        points.append([xc, yc])
    return np.asarray(points)


def peek_bonding_disp(points_3d, rotvec):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(subplot_kw={'projection': '3d'})
    ax.scatter(points_3d[:, 0], points_3d[:, 1], points_3d[:, 2], color='C0')
    ax.quiver(
        points_3d[:, 0], points_3d[:, 1], points_3d[:, 2],
        rotvec[:, 0], rotvec[:, 1], rotvec[:, 2],
        normalize=False, color='C1',
    )
    ax.set_title('Mapped points with rotation vectors')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.axis('equal')
    plt.show()


BONDING_DISP_HEADER = """# Bonding regions displacement data file
#
# This file specifies the displacement and rotation for each bonding region
# listed in `bonding.txt`, following the same order as in that file.
#
# Each line corresponds to a bonding region and contains:
#
#   {U1} {U2} {U3} {UR1} {UR2} {UR3}
#
#   where (U1, U2, U3) are the displacement components, and (UR1, UR2, UR3) are
#   the rotational displacement components (in radians).

"""


if __name__ == '__main__':
    points_2d = load_bonding_points_from_file()
    points_3d, rotvec = my_map(points_2d)

    peek_bonding_disp(points_3d, rotvec)

    with open('bonding_disp.txt', 'w') as f:
        f.write(BONDING_DISP_HEADER)
        for i in range(len(points_2d)):
            u, v = points_2d[i]
            x, y, z = points_3d[i]
            urx, ury, urz = rotvec[i]
            f.write(
                '{:13.6e} {:13.6e} {:13.6e} {:13.6e} {:13.6e} {:13.6e}\n'
                .format(x-u, y-v, z, urx, ury, urz)
            )
    print('Bonding displacement data written to "bonding_disp.txt".')
