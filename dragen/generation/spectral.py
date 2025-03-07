"""
INPUT FOR DAMASK 3 from here on!
"""
import damask
import numpy as np
import pandas as pd
from dragen.utilities.InputInfo import RveInfo
import pyvista as pv
import os
import yaml


def write_material(store_path: str, grains: list, angles: pd.DataFrame) -> None:
    matdata = damask.ConfigMaterial()

    # Homog
    matdata['homogenization']['SX'] = {'N_constituents': 1, 'mechanical': {'type': 'pass'}}

    # Phase
    ferrite = {'lattice': 'cI',
               'mechanical':
                   {'output': ['F', 'P'],
                    'elastic': {'type': 'Hooke', 'C_11': 233.3e9, 'C_12': 135.5e9, 'C_44': 128e9},
                    'plastic': {'type': 'phenopowerlaw',
                                'N_sl': [12, 12],
                                'a_sl': 4.5,
                                'atol_xi': 1,
                                'dot_gamma_0_sl': 0.001,
                                'h_0_sl-sl': 625e6,
                                'h_sl-sl': [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
                                'n_sl': 5,
                                'xi_0_sl': [150e6, 150e6],
                                'xi_inf_sl': [400e6, 400e6]
                                }
                    }
               }

    martensite = {'lattice': 'cI',
                  'mechanical':
                      {'output': ['F', 'P'],
                       'elastic': {'type': 'Hooke', 'C_11': 417.4e9, 'C_12': 242.4e9, 'C_44': 211.1e9},
                       'plastic': {'type': 'isotropic',
                                   'xi_0': 250000000,
                                   'xi_inf': 750000000,
                                   'dot_gamma_0': 0.001,
                                   'n': 30,
                                   'M': 3,
                                   'h_0': 2500000000,
                                   'a': 1.25,
                                   'dilatation': False
                                   }
                       }
                  }

    inclusion = {'lattice': 'cI',
                 'mechanical':
                     {'output': ['F', 'P'],
                      'elastic': {'type': 'Hooke', 'C_11': 417.4e10, 'C_12': 242.4e10, 'C_44': 211.1e10},
                      }
                 }

    matdata['phase']['Ferrite'] = ferrite
    matdata['phase']['Martensite'] = martensite
    if 6 in grains:
        matdata['phase']['ThirdPhase'] = inclusion

    # Material
    i = 0
    for p in grains:
        if p == 1:
            o = damask.Rotation.from_Euler_angles(angles.loc[i].to_numpy(), degrees=True)
            matdata = matdata.material_add(phase=['Ferrite'], O=o,
                                           homogenization='SX')
        elif p == 2:
            matdata = matdata.material_add(phase=['Martensite'], O=damask.Rotation.from_random(1),
                                           homogenization='SX')
        elif p == 6:
            matdata = matdata.material_add(phase=['ThirdPhase'], O=damask.Rotation.from_random(1),
                                           homogenization='SX')
        i += 1

    print('Anzahl materialien in Materials.yaml: ', grains.__len__())
    matdata.save(store_path + '/material.yaml')


def write_load(store_path: str) -> None:
    load_case = damask.Config(solver={'mechanical': 'spectral_polarization'},
                              loadstep=[])

    F = ['x', 0, 0, 0, 'x', 0, 0, 0, 2e-2]
    P = ['x' if i != 'x' else 0 for i in F]

    load_case['loadstep'].append({'boundary_conditions': {},
                                  'discretization': {'t': 10., 'N': 100}, 'f_out': 4})
    load_case['loadstep'][0]['boundary_conditions']['mechanical'] = \
        {'P': [P[0:3], P[3:6], P[6:9]],
         'dot_F': [F[0:3], F[3:6], F[6:9]]}

    load_case.save(store_path + '/load.yaml')


def write_grid(store_path: str, rve: np.ndarray, spacing: float) -> None:
    if rve.dtype != np.int64:
        rve = rve.astype('int64')
    rve = rve - 1
    grid = damask.Grid(material=rve, size=[spacing, spacing, spacing])

    print('Anzahl Materialien im Grid', grid.N_materials)

    grid.save(fname=store_path + '/grid.vti', compress=True)
    vtk_grid = pv.read(store_path + '/grid.vti')
    vtk_grid.save(store_path + '/grid.vtk')

    grid2 = pv.read(os.path.join(store_path, r'grid.vti'))
    
    grid2['phi'] = [1 for i in range(rve.shape[0]**3)]
 
    with open(os.path.join(store_path, r'material.yaml'), 'r') as ym:
        ym = yaml.safe_load(ym)
    
    mat = ym['material']
    n_ferrite = 0
    n_martensite = 0
    phase_list = list()
    for m in mat:
        phase = m['constituents'][0]['phase']
        if 'Ferrite' in phase:
            n_ferrite += 1
            phase_list.append(1)
        else:
            n_martensite += 1
            phase_list.append(2)
    
    ferrite_vox = 0
    martensite_vox = 0
    phase_array = np.zeros(grid2['material'].__len__())
    for k in range(phase_list.__len__()):
        grain_vol = np.count_nonzero(grid2['material'] == k)
        if phase_list[k] == 1:
            ferrite_vox += grain_vol
            points = grid2['material'].flatten(order='F') == k
            phase_array[points] = 0
        else:
            martensite_vox += grain_vol
            points = grid2['material'].flatten(order='F') == k
            phase_array[points] = 1
    
    grid2['phases'] = phase_array
    
    grid2.save(os.path.join(store_path, r'grid.vti'))