# _*_ coding: utf-8 _*_
"""
Time:     2021/7/24 12:03
Author:   Linghao Kong
Version:  V 0.1
File:     mesh_substructure
Describe: Write during the internship at IEHK RWTH"""

import pandas as pd
from dragen.generation.mesher import Mesher
import pyvista as pv
import numpy as np
import tetgen
import datetime

def gen_substruct(self):

    grid = self.gen_blocks()
    grid = self.gen_grains(grid)

    rve = self.rve
    rve.sort_values(by=['x', 'y', 'z'], inplace=True)
    grid.cell_arrays['packet_id'] = rve.packet_id #assign nodes with values in dict way
    grid.cell_arrays['block_id'] = rve.block_id

    if self.animation:

        plotter = pv.Plotter(off_screen=True)
        plotter.add_mesh(grid, scalars='packet_id', stitle='block_ids',
                         show_edges=True,
                         interpolate_before_map=True)  # different packet_id attribute of cell_arrays given different color
        plotter.add_axes()
        plotter.show(interactive=True, auto_close=True, window_size=[800, 600],
                     screenshot='./Figs/pyvista_Hex_Mesh_blocks.png')
        plotter.close()

        plotter = pv.Plotter(off_screen=True)
        plotter.add_mesh(grid, scalars='block_id', stitle='block_ids',
                         show_edges=True,
                         interpolate_before_map=True)  # different block_id attribute of cell_arrays given different color
        plotter.add_axes()
        plotter.show(interactive=True, auto_close=True, window_size=[800, 600],
                     screenshot='./Figs/pyvista_Hex_Mesh_blocks.png')
        plotter.close()

    return grid

def subs_to_mesh(self,grid):

    all_points = grid.points
    all_points_df = pd.DataFrame(all_points, columns=['x', 'y', 'z'], dtype=float)
    all_points_df.sort_values(by=['x', 'y', 'z'], inplace=True)

    grainboundary_df = pd.DataFrame()
    for i in range(1,self.n_blocks+1):
        sub_grid = grid.extract_cells(np.where(np.asarray(grid.cell_arrays.values())[3] == i))
        sub_surf = sub_grid.extract_surface()
        sub_surf.triangulate(inplace=True)

        p = sub_surf.points
        p_df = pd.DataFrame(p, columns=['x', 'y', 'z'], dtype=float)
        p_df.sort_values(by=['x', 'y', 'z'], inplace=True)
        compare_all = all_points_df.merge(p_df, on=['x', 'y', 'z'], how='left', indicator=True)
        compare_grain = compare_all.loc[compare_all['_merge'] == 'both'].copy()  # find the corresponding data fast

        compare_grain.reset_index(inplace=True)
        compare_grain['block_idx'] = p_df.index
        compare_grain.sort_values(by=['block_idx'], inplace=True)

        faces = sub_surf.faces
        faces = np.reshape(faces, (int(len(faces) / 4), 4))  # number of nodes, nodes idx
        f_df = pd.DataFrame(faces, columns=['nnds', 'p1', 'p2', 'p3'])
        idx = np.asarray(compare_grain['index'])  # reindex from whole rve
        f_df['p1'] = [idx[j] for j in f_df['p1'].values]
        f_df['p2'] = [idx[j] for j in f_df['p2'].values]
        f_df['p3'] = [idx[j] for j in f_df['p3'].values]
        f_df['facelabel'] = str(i)

        grainboundary_df = pd.concat([grainboundary_df, f_df])

    sorted_tuple = [[grainboundary_df.p1.values[i],
                     grainboundary_df.p2.values[i],
                     grainboundary_df.p3.values[i]]
                    for i in range(len(grainboundary_df))]

    sorted_tuple = [sorted(item) for item in sorted_tuple]  # sorted nodes in each face
    sorted_tuple = [tuple(item) for item in sorted_tuple]

    grainboundary_df['sorted_tris'] = sorted_tuple
    unique_grainboundary_df = grainboundary_df.drop_duplicates(subset=['sorted_tris'], keep='first')

    all_faces = unique_grainboundary_df.drop(['sorted_tris','facelabel'], axis=1)
    all_faces = np.array(all_faces, dtype='int32')
    all_faces = np.reshape(all_faces, (1, int(len(all_faces) * 4)))[0]  # reform in shape of polydata
    boundaries = pv.PolyData(all_points, all_faces)

    return boundaries, grainboundary_df

def abaqus_subs_model(self,poly_data: pv.PolyData, rve: pv.UniformGrid,
                      fl: list, tri_df: pd.DataFrame = pd.DataFrame()) -> None:
    """building the mesh_practice model here so far only single phase supported
            for dual or multiple phase material_def needs to be adjusted"""

    fl_df = pd.DataFrame(fl)
    tri = tri_df.drop(['facelabel', 'sorted_tris'], axis=1)
    tri = np.asarray(tri)
    smooth_points = poly_data.points

    f = open(self.store_path + '/RVE_smooth.inp', 'w+')
    f.write('*Heading\n')
    f.write('** Job name: Job-1 Model name: Job-1\n')
    f.write('** Generated by: DRAGen \n')
    f.write('** Date: {}\n'.format(datetime.datetime.now().strftime("%d.%m.%Y")))
    f.write('** Time: {}\n'.format(datetime.datetime.now().strftime("%H:%M:%S")))
    f.write('*Preprint, echo=NO, model=NO, history=NO, contact=NO\n')
    f.write('**\n')
    f.write('** PARTS\n')
    f.write('**\n')
    f.close()

    x_min = min(rve.x)
    y_min = min(rve.y)
    z_min = min(rve.z)
    x_max = max(rve.x)
    y_max = max(rve.y)
    z_max = max(rve.z)

    fail_bid_list = []
    bid_list = []
    pid_list = []
    gid_list = []

    for i in range(self.n_blocks):

        bid = i + 1
        tri_idx = fl_df.loc[(fl_df[0] == bid) | (fl_df[1] == bid)].index
        triGrain = tri[tri_idx, :]
        faces = triGrain.astype('int32')
        sub_surf = pv.PolyData(smooth_points, faces)

        tet = tetgen.TetGen(sub_surf)
        try:
            if self.elem == 'C3D4':
                tet.tetrahedralize(order=1, mindihedral=10, minratio=1.5, supsteiner_level=1)
            elif self.elem == 'C3D10':
                tet.tetrahedralize(order=2, mindihedral=10, minratio=1.5, supsteiner_level=1)
            sub_grid = tet.grid  # grid 1

        except Exception as e:

            fail_bid_list.append(bid)
            print(e)
            print('failed bid cannot tet is:',bid)
            continue

        """
        This following code block is only needed if all grains are generated as independent parts
        and are merged together later. Or if cohesive contact definitions are defined.
        A first attempt for cohesive contact defs led to convergence issues which is why this route
        wasn't followed any further
        """
        # grain_hull_df = pd.DataFrame(sub_grid.points.tolist(), columns=['x', 'y', 'z'])
        # grain_hull_df = gridPointsDf.loc[(gridPointsDf['x'] == x_max) | (gridPointsDf['x'] == x_min) |
        #                                (gridPointsDf['y'] == y_max) | (gridPointsDf['y'] == y_min) |
        #                                (gridPointsDf['z'] == z_max) | (gridPointsDf['z'] == z_min)]
        # grain_hull_df['GrainID'] = nGrain
        # grid_hull_df = pd.concat([grid_hull_df, grain_hull_df])

        ncells = sub_grid.n_cells
        print(i, ncells)
        blockIDList = [i + 1]
        packetIDList = [self.bid_to_pid(i+1)]
        grainIDList = [self.bid_to_gid(i+1)]
        blockID_array = blockIDList * ncells
        packetID_array = packetIDList * ncells
        grainID_array = grainIDList * ncells
        bid_list.extend(blockID_array)
        pid_list.extend(packetID_array)
        gid_list.extend(grainID_array)
        if i == 0:
            grid = sub_grid  # grid2
        else:
            grid = sub_grid.merge(grid)  # grid3


    grid.cell_arrays['block_id'] = bid_list
    grid.cell_arrays['packet_id'] = pid_list
    grid.cell_arrays['GrainID'] = gid_list

    pv.save_meshio(self.store_path + '/rve-part.inp', grid)

    with open(self.store_path + '/rve-part.inp', 'r') as f:
        lines = f.readlines()

    startingLine = lines.index('*NODE\n')

    with open(self.store_path + '/RVE_smooth.inp', 'a') as f:

        f.write('*Part, name=PART-1\n')

        for line in lines[startingLine:]:
            f.write(line)

        for i in range(self.n_blocks):

            nBlock = i + 1
            cells = np.where(grid.cell_arrays['block_id'] == nBlock)[0]

            f.write('*Elset, elset=Set-Block{}\n'.format(nBlock))
            for j, cell in enumerate(cells + 1):
                if (j + 1) % 16 == 0:
                    f.write('\n')
                f.write(' {},'.format(cell))
            f.write('\n')

        for i in range(self.n_packets):

            nPacket = i + 1
            cells = np.where(grid.cell_arrays['packet_id'] == nPacket)[0]

            f.write('*Elset, elset=Set-Packet{}\n'.format(nPacket))
            for j, cell in enumerate(cells + 1):
                if (j + 1) % 16 == 0:
                    f.write('\n')
                f.write(' {},'.format(cell))
            f.write('\n')

        for i in range(self.n_grains):

            nGrain = i + 1
            cells = np.where(grid.cell_arrays['GrainID'] == nGrain)[0]

            f.write('*Elset, elset=Set-Grain{}\n'.format(nGrain))
            for j, cell in enumerate(cells + 1):
                if (j + 1) % 16 == 0:
                    f.write('\n')
                f.write(' {},'.format(cell))
            f.write('\n')


        phase1_idx = 0
        phase2_idx = 0
        for i in range(self.n_blocks):
            nBlock = i + 1
            if self.rve.loc[rve['block_id'] == nBlock].phaseID.values[0] == 1:
                phase1_idx += 1
                f.write('** Section: Section - Block{}\n'.format(nBlock))
                f.write('*Solid Section, elset=Set-Block{}, material=Ferrite_{}\n'.format(nBlock, phase1_idx))
            elif self.rve.loc[rve['block_id'] == nBlock].phaseID.values[0] == 2:
                if not self.phase_two_isotropic:
                    phase2_idx += 1
                    f.write('** Section: Section - Block{}\n'.format(nBlock))
                    f.write('*Solid Section, elset=Set-Block{}, material=Martensite_{}\n'.format(nBlock, phase2_idx))
                else:
                    f.write('** Section: Section - Block{}\n'.format(nBlock))
                    f.write('*Solid Section, elset=Set-Block{}, material=Martensite\n'.format(nBlock))

        # phase1_idx = 0
        # phase2_idx = 0
        # for i in range(self.n_packets):
        #     nPacket = i + 1
        #     if self.rve.loc[rve['packet_id'] == nPacket].phaseID.values[0] == 1:
        #         phase1_idx += 1
        #         f.write('** Section: Section - Packet{}\n'.format(nPacket))
        #         f.write('*Solid Section, elset=Set-Packet{}, material=Ferrite_{}\n'.format(nPacket, phase1_idx))
        #     elif self.rve.loc[rve['packet_id'] == nPacket].phaseID.values[0] == 2:
        #         if not self.phase_two_isotropic:
        #             phase2_idx += 1
        #             f.write('** Section: Section - Packet{}\n'.format(nPacket))
        #             f.write('*Solid Section, elset=Set-Packet{}, material=Martensite_{}\n'.format(nPacket, phase2_idx))
        #         else:
        #             f.write('** Section: Section - Packet{}\n'.format(nPacket))
        #             f.write('*Solid Section, elset=Set-Packet{}, material=Martensite\n'.format(nPacket))
        #
        # phase1_idx = 0
        # phase2_idx = 0
        # for i in range(self.n_grains):
        #     nGrain = i + 1
        #     if self.rve.loc[rve['GrainID'] == nGrain].phaseID.values[0] == 1:
        #         phase1_idx += 1
        #         f.write('** Section: Section - Grain{}\n'.format(nGrain))
        #         f.write('*Solid Section, elset=Set-Grain{}, material=Ferrite_{}\n'.format(nGrain, phase1_idx))
        #     elif self.rve.loc[rve['GrainID'] == nGrain].phaseID.values[0] == 2:
        #         if not self.phase_two_isotropic:
        #             phase2_idx += 1
        #             f.write('** Section: Section - Grain{}\n'.format(nGrain))
        #             f.write('*Solid Section, elset=Set-Grain{}, material=Martensite_{}\n'.format(nGrain, phase2_idx))
        #         else:
        #             f.write('** Section: Section - Grain{}\n'.format(nGrain))
        #             f.write('*Solid Section, elset=Set-Grain{}, material=Martensite\n'.format(nGrain))

    grid_hull_df = pd.DataFrame(grid.points.tolist(), columns=['x', 'y', 'z'])
    grid_hull_df = grid_hull_df.loc[(grid_hull_df['x'] == x_max) | (grid_hull_df['x'] == x_min) |
                                                (grid_hull_df['y'] == y_max) | (grid_hull_df['y'] == y_min) |
                                                (grid_hull_df['z'] == z_max) | (grid_hull_df['z'] == z_min)]

    self.make_assembly()  # Don't change the order
    self.pbc(rve, grid_hull_df)  # of these four
    self.write_material('block')
    self.write_step_def()  # it will lead to a faulty inputfile
    self.write_block_data()

    return fail_bid_list

def write_material(self,sub):
    phase1_idx = 0
    phase2_idx = 0

    if sub == "grain":
        numberofsub = self.n_grains
        phase = [self.rve.loc[self.rve['GrainID'] == i].phaseID.values[0] for i in range(1, numberofsub + 1)]
    if sub =="packet":
        numberofsub = self.n_packets
        phase = [self.rve.loc[self.rve['packet_id'] == i].phaseID.values[0] for i in range(1, numberofsub + 1)]
    if sub == "block":
        numberofsub = self.n_blocks
        phase = [self.rve.loc[self.rve['block_id'] == i].phaseID.values[0] for i in range(1, numberofsub + 1)]

    #phase = [self.rve.loc[self.rve['GrainID'] == i].phaseID.values[0] for i in range(1, numberofsub + 1)]
    with open(self.store_path + '/RVE_smooth.inp', 'a') as f:

        f.write('**\n')
        f.write('** MATERIALS\n')
        f.write('**\n')
        for i in range(numberofsub):
            ngrain = i + 1
            if not self.phase_two_isotropic:
                if phase[i] == 1:
                    phase1_idx += 1
                    f.write('*Material, name=Ferrite_{}\n'.format(phase1_idx))
                    f.write('*Depvar\n')
                    f.write('    176,\n')
                    f.write('*User Material, constants=2\n')
                    f.write('{}.,3.\n'.format(ngrain))
                elif phase[i] == 2:
                    phase2_idx += 1
                    f.write('*Material, name=Martensite_{}\n'.format(phase2_idx))
                    f.write('*Depvar\n')
                    f.write('    176,\n')
                    f.write('*User Material, constants=2\n')
                    f.write('{}.,4.\n'.format(ngrain))
            else:
                if phase[i] == 1:
                    phase1_idx += 1
                    f.write('*Material, name=Ferrite_{}\n'.format(phase1_idx))
                    f.write('*Depvar\n')
                    f.write('    176,\n')
                    f.write('*User Material, constants=2\n')
                    f.write('{}.,3.\n'.format(phase1_idx))

        if self.phase_two_isotropic:
            f.write('**\n')
            f.write('*Material, name=Martensite\n')
            f.write('*Elastic\n')
            f.write('0.21, 0.3\n')

def write_block_data(self):
    f = open(self.store_path + '/graindata.inp', 'w+')
    f.write('!MMM Crystal Plasticity Input File\n')
    phase1_idx = 0
    numberofblocks = self.n_blocks
    phase = [self.rve.loc[self.rve['block_id'] == i].phaseID.values[0] for i in range(1, numberofblocks + 1)]
    grainsize = [1 for i in range(1, numberofblocks + 1)]

    block_list = list(set(self.rve['block_id']))
    groups = self.rve.groupby('block_id').head(1)  # first line of data, type:dataframe

    angle_list = groups.apply(lambda p: self.comp_angle(self.grains_df, p), axis=1)
    bid_to_angle = dict(zip(block_list, angle_list))

    for i in range(numberofblocks):
        nblock = i + 1
        if not self.phase_two_isotropic:
            """phi1 = int(np.random.rand() * 360)
            PHI = int(np.random.rand() * 360)
            phi2 = int(np.random.rand() * 360)"""
            phi1 = bid_to_angle[i][0]
            PHI = bid_to_angle[i][1]
            phi2 = bid_to_angle[i][2]
            f.write('Block: {}: {}: {}: {}: {}\n'.format(nblock, phi1, PHI, phi2, grainsize[i]))
        else:
            if phase[i] == 1:
                phase1_idx += 1
                """phi1 = int(np.random.rand() * 360)
                PHI = int(np.random.rand() * 360)
                phi2 = int(np.random.rand() * 360)"""
                phi1 = bid_to_angle[i][0]
                PHI = bid_to_angle[i][1]
                phi2 = bid_to_angle[i][2]
                f.write('Block: {}: {}: {}: {}: {}\n'.format(phase1_idx, phi1, PHI, phi2, grainsize[i]))
    f.close()

def bid_to_pid(self, bid):
    pid_list = self.rve.loc[rve['block_id'] == bid, 'packet_id']

    return int(pid_list.iloc[0])

def bid_to_gid(self, bid):
    gid_list = self.rve.loc[rve['block_id'] == bid, 'GrainID']

    return int(gid_list.iloc[0])

def comp_angle(self,grain_data,point_data):  #may cause invalid value for arc
    T_list = [np.array(0) for i in range(24)]

    T_list[0] = np.array([[0.742, 0.667, 0.075],
                          [0.650, 0.742, 0.167],
                          [0.167, 0.075, 0.983]])

    T_list[1] = np.array([[0.075, 0.667, -0.742],
                          [-0.167, 0.742, 0.650],
                          [0.983, 0.075, 0.167]])

    T_list[2] = np.array([[-0.667, -0.075, 0.742, ],
                          [0.742, -0.167, 0.650],
                          [0.075, 0.983, 0.167]])

    T_list[3] = np.array([[0.667, -0.742, 0.075],
                          [0.742, 0.650, -0.167],
                          [0.075, 0.167, 0.983]])

    T_list[4] = np.array([[-0.075, 0.742, -0.667],
                          [-0.167, 0.650, 0.742],
                          [0.983, 0.167, 0.075]])

    T_list[5] = np.array([[-0.742, 0.075, 0.667],
                          [0.650, -0.167, 0.742],
                          [0.167, 0.983, 0.075]])

    T_list[6] = np.array([[-0.075, 0.667, 0.742],
                          [-0.167, -0.742, 0.650],
                          [0.983, -0.075, 0.167]])

    T_list[7] = np.array([[-0.742, -0.667, 0.075],
                          [0.650, -0.742, -0.167],
                          [0.167, -0.075, 0.983]])

    T_list[8] = np.array([[0.742, 0.075, -0.667],
                          [0.650, 0.167, 0.742],
                          [0.167, -0.983, 0.075]])

    T_list[9] = np.array([[0.075, 0.742, 0.667],
                          [-0.167, -0.650, 0.742],
                          [0.983, -0.167, 0.075]])

    T_list[10] = np.array([[-0.667, -0.742, -0.075],
                           [0.742, -0.650, -0.167],
                           [0.075, -0.167, 0.983]])

    T_list[11] = np.array([[0.667, -0.075, -0.742],
                           [0.742, 0.167, 0.650],
                           [0.075, -0.983, 0.167]])

    T_list[12] = np.array([[0.667, 0.742, -0.075],
                           [-0.742, 0.650, -0.167],
                           [-0.075, 0.167, 0.983]])

    T_list[13] = np.array([[-0.667, 0.075, -0.742],
                           [-0.742, -0.167, 0.650],
                           [-0.075, 0.983, 0.167]])

    T_list[14] = np.array([[0.075, -0.667, 0.742],
                           [0.167, 0.742, 0.650],
                           [-0.983, 0.075, 0.167]])

    T_list[15] = np.array([[0.742, 0.667, 0.075],
                           [-0.650, 0.742, -0.167],
                           [-0.167, 0.075, 0.983]])

    T_list[16] = np.array([[-0.742, 0.075, -0.667],
                           [-0.650, -0.167, 0.742],
                           [-0.167, 0.983, 0.075]])

    T_list[17] = np.array([[-0.075, -0.742, 0.667],
                           [0.167, 0.650, 0.742],
                           [-0.983, 0.167, 0.075]])

    T_list[18] = np.array([[0.742, -0.075, 0.667],
                           [0.650, -0.167, -0.742],
                           [0.167, 0.983, -0.075]])

    T_list[19] = np.array([[0.075, -0.742, -0.667],
                           [-0.167, 0.650, -0.742],
                           [0.983, 0.167, -0.075]])

    T_list[20] = np.array([[-0.667, 0.742, 0.075],
                           [0.742, 0.650, 0.167],
                           [0.075, 0.167, -0.983]])

    T_list[21] = np.array([[0.667, 0.075, 0.742],
                           [0.742, -0.167, -0.650],
                           [0.075, 0.983, -0.167]])

    T_list[22] = np.array([[-0.075, -0.667, -0.742],
                           [-0.167, 0.742, -0.650],
                           [0.983, 0.075, -0.167]])

    T_list[23] = np.array([[-0.742, 0.667, -0.075],
                           [0.650, 0.742, 0.167],
                           [0.167, 0.075, -0.983]])

    gid = point_data['GrainID']

    if point_data['phaseID'] == 1:

        return grain_data.loc[grain_data['GrainID'] == gid, 'phi1'].values[0], \
               grain_data.loc[grain_data['GrainID'] == gid, 'PHI'].values[0], \
               grain_data.loc[grain_data['GrainID'] == gid, 'phi2'].values[0]

    if point_data['phaseID'] == 2:

        try:
            i = int(str(point_data['block_orientation']).lstrip('V')) - 1

        except:
            i = np.random.randint(24) #needs modification

        T = T_list[i]
        phi1 = grain_data.loc[grain_data['GrainID'] == gid, 'phi1'].values[0]
        PHI = grain_data.loc[grain_data['GrainID'] == gid, 'PHI'].values[0]
        phi2 = grain_data.loc[grain_data['GrainID'] == gid, 'phi2'].values[0]

        R1 = np.array([[np.cos(np.deg2rad(phi1)), -np.sin(np.deg2rad(phi1)), 0],
                       [np.sin(np.deg2rad(phi1)), np.cos(np.deg2rad(phi1)), 0],
                       [0, 0, 1]])

        R2 = np.array([[1, 0, 0],
                       [0, np.cos(np.deg2rad(PHI)), -np.sin(np.deg2rad(PHI))],
                       [0, np.sin(np.deg2rad(PHI)), np.cos(np.deg2rad(PHI))]])

        R3 = np.array([[np.cos(np.deg2rad(phi2)), -np.sin(np.deg2rad(phi2)), 0],
                       [np.sin(np.deg2rad(phi2)), np.cos(np.deg2rad(phi2)), 0],
                       [0, 0, 1]])

        result = np.dot(R3, R2)
        R = np.matrix(np.dot(result, R1))

        RB = T*R

        PHIB = np.degrees(np.arccos(RB[2,2]))
        sin_PHIB = np.sin(np.deg2rad(PHIB))
        phi1B = np.degrees(np.arcsin(RB[2,0]/sin_PHIB))
        phi2B = np.degrees(np.arcsin(RB[0,2]/sin_PHIB))

        return phi1B,PHIB,phi2B

Mesher.gen_substruct = gen_substruct
Mesher.subs_to_mesh = subs_to_mesh
Mesher.abaqus_subs_model = abaqus_subs_model
Mesher.write_material = write_material
Mesher.bid_to_pid = bid_to_pid
Mesher.bid_to_gid = bid_to_gid
Mesher.comp_angle = comp_angle
Mesher.write_block_data = write_block_data

if __name__ == "__main__":

    rve = pd.read_csv('F:/pycharm/2nd_mini_thesis/mesh_practice/final_input/07.26.2021--2/mesh_rve.csv')
    grains_df = pd.read_csv('F:/pycharm/2nd_mini_thesis/mesh_practice/final_input/07.26.2021--2/grains.csv')

    rve.n_pts = [40 for i in range(len(rve))]
    rve.box_size = [20 for i in range(len(rve))]
    mesh = Mesher(rve, grains_df, './final_input/07.26.2021--2',phase_two_isotropic=False, animation=False)

    grid = mesh.gen_substruct()
    boundaries, tri_df = mesh.subs_to_mesh(grid)
    facelabel = mesh.gen_face_labels(tri_df)
    smooth_rve = mesh.smooth(boundaries, grid, tri_df, facelabel)
    mesh.abaqus_subs_model(smooth_rve, grid, facelabel, tri_df)

