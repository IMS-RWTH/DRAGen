import numpy as np
import pandas as pd
from dragen.utilities.InputInfo import RveInfo
import cv2


class shape:
    def __init__(self):
        pass

    def thresh_callback(self, img, max_id, phaseID):

        a = list()
        b = list()
        slope = list()
        thresholds = np.asarray(np.unique(img, return_counts=True)).T
        input_df = pd.read_csv(RveInfo.store_path + '/Generation_Data/grain_data_output_discrete.csv')

        for t in thresholds:
            grain_id = int(t[0]*max_id)
            phase = input_df.loc[grain_id, 'phaseID']
            if phase == phaseID:
                grain = np.zeros_like(img)
                grain[img == t[0]] = 1
                th, threshed = cv2.threshold(grain, t[0], max_id, cv2.THRESH_BINARY)

                # findContours, then fitEllipse for each contour.
                cnts, hiers = cv2.findContours(np.asarray(threshed*255, dtype=np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2:]
                plot_img = np.dstack([img, img, img])
                for cnt in cnts:
                    if cnt.__len__() < 5:
                        continue
                    elps = cv2.fitEllipse(cnt)
                    try:
                        cv2.ellipse(plot_img, elps, (255, 0, 255), 1, cv2.LINE_AA)
                        alpha = elps[2]  # np.rad2deg(elps[2])
                        if 45 < np.rad2deg(elps[2]) < 135:
                            if alpha >= 90:
                                a.append(elps[1][1] / (2*RveInfo.resolution))
                                b.append(elps[1][0] / (2*RveInfo.resolution))
                                slope.append(alpha)
                            else:
                                a.append(elps[1][1] / (2 * RveInfo.resolution))
                                b.append(elps[1][0] / (2 * RveInfo.resolution))
                                slope.append(alpha)
                        else:
                            if alpha >= 90:
                                a.append(elps[1][0] / (2 * RveInfo.resolution))
                                b.append(elps[1][1] / (2 * RveInfo.resolution))
                                slope.append(alpha)

                            else:
                                a.append(elps[1][0] / (2 * RveInfo.resolution))
                                b.append(elps[1][1] / (2 * RveInfo.resolution))
                                slope.append(alpha)
                    except:
                        print('fail')

        AR = [b[i]/a[i] for i in range(len(a)) if (a[i] > 0) and (b[i]/a[i]) < 100]
        slope = [slope[i] for i in range(len(a)) if a[i] > 0 and (b[i]/a[i]) < 100]
        ell_dict = {'AR': AR, 'slope': slope}
        ell_data = pd.DataFrame(ell_dict)

        return ell_data

    def get_ellipses(self, grid, slice_ID, phaseID):

        start1 = int(grid.shape[0] / 4)
        stop1 = int(grid.shape[0] / 4 + grid.shape[0] / 4 * 2)
        start2 = int(grid.shape[1] / 4)
        stop2 = int(grid.shape[1] / 4 + grid.shape[1] / 4 * 2)
        start3 = int(grid.shape[2] / 4)
        stop3 = int(grid.shape[2] / 4 + grid.shape[2] / 4 * 2)
        rve = grid[start1:stop1, start2:stop2, start3:stop3]
        rve = rve - 1  # Grid.vti starts at zero
        max_id = rve.max()
        rve = rve/rve.max()
        slice = rve[:, :, slice_ID]

        data = self.thresh_callback(slice, max_id, phaseID)
        return data

    @staticmethod
    def get_input_ellipses():
        input_df = pd.read_csv(RveInfo.store_path + '/Generation_Data/experimental_data.csv')
        mask = (input_df['a'] > input_df['b'])
        input_df.loc[mask, 'AR'] = input_df['a'] / input_df['b']
        input_df.loc[~mask, 'AR'] = input_df['b'] / input_df['a']

        data = input_df[['phaseID', 'AR', 'alpha']]
        data['inout'] = 'in'
        data = data.rename(columns={'alpha': 'slope'})
        return data


