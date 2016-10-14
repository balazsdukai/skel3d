import math, sys
from time import time
import numpy as np

from itertools import chain
from PyQt5.QtCore import Qt
from pyqtgraph import PlotWidget, LinearRegionItem

from scipy.stats import linregress

from povi import App, Layer, LinkedLayer, ToolsDialog
from skel3d.io import npy
from skel3d.util import MAHelper
from skel3d.graph import *
from skel3d.segmentation import *
from skel3d.polyhedralise import *

class TestApp(App):

    def __init__(self, ma, args=[]):
        super(TestApp, self).__init__(args)
        self.ma = ma

    def run(self):
        # self.addGraphWindow()
        self.layer_manager.add_layer(Layer(name='Clusters', is_aggregate=True))
        # here all layers need to have been added
        self.dialog = ToolsWindow(self)
        self.draw_clusters()
        super(TestApp, self).run()
        
        # self.plotWindow.plot(np.random.normal(size=100), name="Data 1")

    def draw_clusters(self):

        ## Remove insignificant edges in graph
        min_count = 50 #self.dialog.ui.spinBox_linkcount.value()
        contract_thres = 15 #self.dialog.ui.doubleSpinBox_contractthres.value()
        # g = g.subgraph(g.vs.select(ma_theta_mean_lt=math.radians(100), up_angle_gt=math.radians(40)))
        master_g = self.ma.D['ma_segment_graph']
        master_g = master_g.subgraph_edges(master_g.es.select(adj_count_gt=min_count))
        # contract_edges(g, contract_thres)

        ## Update segment indices based on graph ids
        ma.D['ma_segment'] = np.zeros(ma.m*2,dtype=np.int64)
        for v in master_g.vs:
            ma.D['ma_segment'][v['ma_idx']] = v.index
            v['s_id'] = v.index
        # flipdic = find_flip_relations(ma)
        
        # self.graphs = []
        # graphlib = get_graph_library()
        # for mapping in g.get_subisomorphisms_vf2(graphlib['flatcube_top']):
        #     self.graphs.append(g.subgraph(mapping))
        
        ## Find clusters, ie. connected component analysis
        self.graphs = master_g.clusters().subgraphs()

        i=0
        for g in self.graphs:
            adj_rel_start = []
            adj_rel_end = []

            if 0<g.ecount():#<1000:

                ## Classify clusters as inside or outside
                # attempt to distinghuish between interior and exterior sheets based on vertical component of bisectors
                color = (1.,0.,0.)
                name = 'cluster {}'.format(i)
                zsum = 0
                ma_idx = np.concatenate(g.vs['ma_idx'])
                
                # select points with good sepangle (eg not 180deg)
                f = np.intersect1d(np.argwhere(ma.D['ma_theta'] < math.pi*0.9), ma_idx)
                # sort on z component of bisector, take 10% lowest and highest, compute ratio of means of that
                l = len(f)
                bz = ma.D['ma_bisec'][f][:,2]
                bz_sort = np.sort(bz )
                b_bot = np.mean(bz_sort[:l//10]) 
                b_top = np.mean(bz_sort[l-l//10:])
                b_ratio = abs(b_top)/abs(b_bot)

                # for v in g.vs:
                #     zsum += v['ma_bisec_mean'][2]#*len(v['ma_idx'])
                # zsum = np.prod(np.sum(np.array(g.vs['ma_bisec_mean'])[:,2], np.array([len(idx) for idx in g.vs['ma_idx']]) ), axis=1)
                # use ration to decide if int or ext cluster. Now
                name_append = " | exterior"
                if b_ratio > 1.05 or b_bot > 0: # completely `closed` or bounded clusters should have ratio closed to one (only occurs in artifical datasets, since DSM never closed)
                    color = (0.,1.,0.)
                    name_append = " | interior"
                    if np.mean(g.vs['ma_theta_mean']) > math.pi/4: # artificial/building structures typically have a large sepangle (compared to terrain features)
                        color = (1.,1.,0.)
                        name_append += " (building)"

                elif b_ratio > 0.95:
                    color = (0.5,0.5,0.5)
                    name_append = ""
                name += name_append

                if 0:
                    # grow 1 flip sheet around this cluster
                    min_flipcount = 10
                    to_add = []
                    for v in g.vs:
                        v['fliplinks'] = {}
                        s_idx = np.concatenate([np.mod(v['ma_idx'], ma.m), ma.D['ma_qidx'][v['ma_idx']]])
                        for s_id in s_idx:
                            s_in = ma.D['ma_segment'][s_id]                        
                            s_out = ma.D['ma_segment'][s_id+ma.m]

                            s_other = s_in
                            if s_in == v['s_id']:
                                s_other = s_out
                            
                            if s_other == 0:
                                continue

                            if s_other in v['fliplinks']:
                                v['fliplinks'][s_other] += 1
                            else:
                                v['fliplinks'][s_other] = 1
                        for s_id, count in v['fliplinks'].items():
                            if count > min_flipcount:
                                to_add.append((v.index, s_id, count))
                    for source, target, count in to_add:
                        g.add_vertex(**master_g.vs[target].attributes())
                        g.add_edge(source, g.vcount()-1, flip_count=count)
                                                


                # name += ' [{}]'.format(b_ratio)

                for e in g.es:
                    adj_rel_start.append(g.vs[e.source]['ma_coords_mean'])
                    adj_rel_end.append(g.vs[e.target]['ma_coords_mean'])
                # color = np.random.uniform(0.3,1.0,3)
                p = self.layer_manager['Clusters'].add_data_source_line(
                    name = name,
                    coords_start = np.array(adj_rel_start),
                    coords_end = np.array(adj_rel_end),
                    color = tuple(color),
                    is_visible=True
                )
                i+=1
                p.graph = g
        self.viewerWindow.render()

        self.layer_manager['Clusters'].is_visible=True
        self.active_graph = None

        # populate comboBox_component
        self.dialog.ui.comboBox_clusters.insertItems(0, ['All']+[name for name in self.layer_manager['Clusters'].programs.keys()])

    def toggle_selection(self, toggle):
        if toggle==True:
            self.filter_cluster(index=self.dialog.ui.comboBox_clusters.currentIndex())
        else:
            self.filter_cluster(0)
            self.filter_idx()
        # self.viewerWindow.render()

    def filter_cluster(self, index):
        if index == 0:
            self.filter_idx(None)
            self.active_graph = None
            self.dialog.ui.comboBox_sheets.clear()
            for program in self.layer_manager['Clusters']:
                program.is_visible=True
            # self.viewerWindow.center_view(self.layer_manager['Clusters'].get_center())
            self.viewerWindow.render()
            return

        for program in self.layer_manager['Clusters']:
            program.is_visible=False
        name = self.dialog.ui.comboBox_clusters.itemText(index)
        self.layer_manager['Clusters'][name].is_visible = True
        
        g = self.layer_manager['Clusters'][name].graph
        self.active_graph = g
        if self.dialog.ui.checkBox_clusterCenterView.isChecked():
            self.viewerWindow.center_view(np.mean(g.vs['ma_coords_mean'], axis=0))
            self.viewerWindow.render()

        ma_idx = np.concatenate(g.vs['ma_idx'])
        # if ma_idx.sum() <1:return
        self.dialog.plot_histogram(ma_idx)
        self.filter_idx(ma_idx)

        # populate sheet list
        self.dialog.ui.comboBox_sheets.clear()
        self.dialog.ui.comboBox_sheets.insertItems(0, ['All']+['Sheet '+str(v.index) for v in g.vs])

    def filter_sheet(self, index):
        if index == 0:
            self.filter_cluster(self.dialog.ui.comboBox_clusters.currentIndex())
        else:
            v = self.active_graph.vs[index-1]
            # if ma_idx.sum() <1:return
            self.dialog.plot_directional_analysis(v)
            if self.dialog.ui.checkBox_sheetCenterView.isChecked():
                self.viewerWindow.center_view(v['ma_coords_mean'])
                self.viewerWindow.render()

            self.filter_idx(v['ma_idx'])
        

    def filter_idx(self, ma_idx=None):
        # update mat points
        if ma_idx is None:
            self.layer_manager['MAT'].mask()
            self.layer_manager['Surface'].mask()
        else:    
            f = np.zeros(self.ma.m*2, dtype=bool)
            f[ma_idx] = True
            self.layer_manager['MAT'].mask(f)

            # find indices of all surface points related to these mat points
            f = np.zeros(self.ma.m, dtype=bool)
            f[np.mod(ma_idx, self.ma.m)] = True
            f[self.ma.D['ma_qidx'][ma_idx]] = True
            self.layer_manager['Surface'].mask(f)
        
        self.viewerWindow.render()
    
    # def addGraphWindow(self): 
    #     self.plotWindow = GraphWindow(master_app=self)
    #     # self.plotWindow.addLegend()
    #     self.plotWindow.show()
    #     # super(TestApp, self).run()

class ToolsWindow(ToolsDialog):
    def __init__(self, app):
        super(ToolsWindow, self).__init__(app, ui_path='sheeterator.ui', parent=None)
        self.ui.graphicsView_plotWidget.showGrid(x=True, y=True, alpha=0.4)
        
        # self.ui.graphicsView_plotWidget.setDownsampling(auto=True, mode='subsample')
        # self.ui.graphicsView_plotWidget.addLegend()

    def connectUI(self):
        super(ToolsWindow, self).connectUI()

        self.ui.comboBox_clusters.activated.connect(self.app.filter_cluster)
        self.ui.comboBox_sheets.activated.connect(self.app.filter_sheet)
        self.ui.groupBox_cluster.clicked.connect(self.app.toggle_selection)

    def keyPressEvent(self, event):
        key = event.key()
        repeat = event.isAutoRepeat()
        # print('keypressevent!')

        if key == Qt.Key_Up:
            newIndex = self.ui.comboBox_clusters.currentIndex() -1
            if newIndex == -1:
                newIndex = self.ui.comboBox_clusters.count() - 1
            self.ui.comboBox_clusters.setCurrentIndex(newIndex)
            self.app.filter_cluster(newIndex)
        if key == Qt.Key_Down:
            newIndex = self.ui.comboBox_clusters.currentIndex() + 1
            if newIndex == self.ui.comboBox_clusters.count():
                newIndex = 0
            self.ui.comboBox_clusters.setCurrentIndex(newIndex)
            self.app.filter_cluster(newIndex)
        if key == Qt.Key_Left:
            newIndex = self.ui.comboBox_sheets.currentIndex() - 1
            if newIndex == -1:
                newIndex = self.ui.comboBox_sheets.count()-1
            self.ui.comboBox_sheets.setCurrentIndex(newIndex)
            self.app.filter_sheet(newIndex)
        if key == Qt.Key_Right:
            newIndex = self.ui.comboBox_sheets.currentIndex() + 1
            if newIndex == self.ui.comboBox_sheets.count():
                newIndex = 0
            self.ui.comboBox_sheets.setCurrentIndex(newIndex)
            self.app.filter_sheet(newIndex)

    def lr_changed(self, lr):
        xmi, xma = lr.getRegion()
        mask = np.logical_and(xmi < self.x, self.x < xma)
        ma_idx = self.ma_idx[mask]
        self.app.filter_idx(ma_idx)

    def plot_directional_analysis(self, v):
        def plot(x,y,color,name):
            self.ui.graphicsView_plotWidget.plot(x, y,  pen=None, symbol='o', symbolPen=None, symbolSize=4, symbolBrush=color, name=name)
            slope, intercept, r_value, p_value, std_err = linregress(x,y)
            x_ = np.linspace(x.min()-1,x.max()+1)
            y_ = x_*slope + intercept
            print(name)
            print('intercept:', str(intercept))
            print('slope:', str(slope))
            print('r_value:', str(r_value))
            print('p_value:', str(p_value))
            print('std_err:', str(std_err))
            self.ui.graphicsView_plotWidget.plot(x_, y_, pen={'color': color}, name=name)
        self.ui.graphicsView_plotWidget.clear()
        # pick reference point: the point with median bisector
        ma_idx = np.array(v['ma_idx'])
        if len(ma_idx)>10000:return
        radii = ma.D['ma_radii'][ma_idx]
        # thetas = ma.D['ma_theta'][ma_idx]
        # c_id = ma_idx[np.argmax(radii)]
        # c_id = ma_idx[np.argsort(thetas)[len(radii)//2]]
        # c_id = np.random.randint(len(ma_idx))

        # r = ma.D['ma_radii'][c_id] #ma.D['coords'][np.mod(c_id, ma.m)] - ma.D['ma_coords'][c_id]
        # theta = ma.D['ma_theta'][c_id]
        # b = ma.D['ma_bisec'][c_id]
        # c = ma.D['ma_coords'][c_id]

        r = np.mean(ma.D['ma_radii'][ma_idx], axis=0)
        theta = np.mean(ma.D['ma_theta'][ma_idx], axis=0)
        b = np.mean(ma.D['ma_bisec'][ma_idx], axis=0)
        c = np.mean(ma.D['ma_coords'][ma_idx], axis=0)

        xc = r/np.cos(theta/2)
        x = np.empty(len(ma_idx))
        for i in range(len(ma_idx)):
            x[i] = xc + (np.dot(c-ma.D['ma_coords'][ma_idx[i]], b))
        self.x = x
        self.ma_idx = ma_idx

        # sort everything? Not needed for scatter plot
        # x_sort = np.argsort(x)
        # ma_idx = ma_idx[x_sort]
        # x = x[x_sort]

        y = ma.D['ma_radii'][ma_idx]
        # color = tuple(np.random.uniform(0.3,1.0,3)*255) + (255,)
        color = (0,220,0,160)
        plot(x,y,color,'Radii')
        
        color = (0,220,220,160)
        y = ma.D['ma_theta'][ma_idx]
        plot(x,y,color,'SepAngle')

        y = np.empty(len(ma_idx))
        for i in range(len(ma_idx)):
            y[i] = angle(b, ma.D['ma_bisec'][ma_idx[i]])
        color = (250,0,0,160)
        plot(x, y, color, 'Bisector diff')
        
        y = np.empty(len(ma_idx))
        for i in range(len(ma_idx)):
            y[i] = 2*np.arccos(ma.D['ma_radii'][ma_idx[i]]/ x[i])
        color = (250,0,255,160)
        plot(x,y,color,name='SepAnglePredict')

        #
        def cluster_spokes(ma,ma_idx):
            cross = np.cross(ma.D['ma_f1'][ma_idx], ma.D['ma_f2'][ma_idx])
            l = Line([Point(v) for v in cross])
            # l.t is a unit vector in one direction of the line
            x = np.empty(len(cross))
            for i, v in enumerate(cross):
                x[i] = np.dot(l.t,v)

            return x > 0, cross

        # define plane at representative point:
        # we need an actual point on the sheet because we can't quickly aggregate spokes, because of their inconsistent orientation
        # c_id = ma_idx[ np.argmin(cdist(ma.D['ma_coords'][ma_idx], np.array([c]))) ]
        # c_id = ma_idx[np.argsort(radii)[len(radii)//2]]
        # c = ma.D['ma_coords'][c_id]
        # f1 = ma.D['ma_f1'][c_id]
        # f2 = ma.D['ma_f2'][c_id]
        # cross product of spokes is perpendicular to bisector and tangent to sheet
        one_side, cross = cluster_spokes(ma, ma_idx)
        # align al crosses and compute average
        cross_align = cross 
        cross_align[~one_side] *= -1  
        # np.concatenate([cross[one_side], -1*cross[~one_side]])
        vec_coplanar = np.mean(cross_align, axis=0)
        # now compute this cross product to find a vector in the normal direction of the plane that we want to reconstruct
        n = np.cross(vec_coplanar, b)
        n = n / np.linalg.norm(n)
        # plane = Plane(pc, Line(pc, pn))
        y = np.empty(len(ma_idx))
        for i in range(len(ma_idx)):
            q = ma.D['ma_coords'][ma_idx[i]] - c
            q_on_n = np.dot(q,n)
            y[i] = q_on_n
            # y[i] = np.linalg.norm(q-q_on_n)
            # y[i] = plane.distance_to(Point(ma.D['ma_coords'][ma_idx[i]]))
        color = (250,250,0,160)
        plot(x, y, color, 'Plane fit')

        # diff in cross
        y = np.empty(len(ma_idx))
        for i in range(len(ma_idx)):
            y[i] = angle(vec_coplanar, cross_align[i])
        color = (200,200,200,160)
        plot(x, y, color, 'Cross diff') 

        xmi, xma = x.min(), x.max() 
        lr = LinearRegionItem([xmi-.1, xma+.1], movable=True)
        self.ui.graphicsView_plotWidget.addItem(lr)
        lr.sigRegionChangeFinished.connect(self.lr_changed)

        # vals=ma.D['spoke_cnt'][ma.D['ma_qidx'][ma_idx]]
        # ## compute standard histogram
        # y,x = np.histogram(vals, bins=50)

        # ## Using stepMode=True causes the plot to draw two lines for each sample.
        # ## notice that len(x) == len(y)+1
        # # color = tuple(np.random.uniform(0.3,1.0,3)*255) + (255,)
        # # color = (0,200,0,255)
        # color = (220,220,25,255)
        # self.ui.graphicsView_plotWidget.plot(x, y, stepMode=True, fillLevel=0, pen={'color': color, 'width': 2}, name='bisec_z '+str(42))


    def plot_histogram(self, ma_idx):
        # self.clear()

        # import ipdb/;ipdb.set_trace()
        # i = v.index
        vals=ma.D['ma_radii'][ma_idx]
        ## compute standard histogram
        y,x = np.histogram(vals, bins=50)

        ## Using stepMode=True causes the plot to draw two lines for each sample.
        ## notice that len(x) == len(y)+1
        # color = tuple(np.random.uniform(0.3,1.0,3)*255) + (255,)
        color = (0,220,0,255)
        self.ui.graphicsView_plotWidget.plot(x, y, stepMode=True, fillLevel=0, pen={'color': color, 'width': 2}, name='radius '+str(42), clear=True)
        
        vals=ma.D['ma_theta'][ma_idx]
        ## compute standard histogram
        y,x = np.histogram(vals, bins=50)

        ## Using stepMode=True causes the plot to draw two lines for each sample.
        ## notice that len(x) == len(y)+1
        # color = tuple(np.random.uniform(0.3,1.0,3)*255) + (255,)
        # color = (0,200,0,255)
        color = (0,220,220,255)
        self.ui.graphicsView_plotWidget.plot(x, y, stepMode=True, fillLevel=0, pen={'color': color, 'width': 2}, name='theta '+str(42))
        
        ## compute histogram of bisector z-components
        vals=ma.D['ma_bisec'][ma_idx,2]
        y,x = np.histogram(vals, bins=50)

        ## Using stepMode=True causes the plot to draw two lines for each sample.
        ## notice that len(x) == len(y)+1
        # color = tuple(np.random.uniform(0.3,1.0,3)*255) + (255,)
        # color = (0,200,0,255)
        color = (220,220,220,255)
        self.ui.graphicsView_plotWidget.plot(x, y, stepMode=True, fillLevel=0, pen={'color': color, 'width': 2}, name='bisec_z '+str(42))
        
# class GraphWindow(PlotWidget):
#     def __init__(self, master_app, parent=None):
#         self.layer_manager = master_app.layer_manager
#         self.master_app = master_app
#         super(GraphWindow, self).__init__(parent)


    


def view(ma, vid):
    # ref_count = timeit(count_refs)
    max_r=190.
    # ma.g = ma.D['ma_segment_graph']
    
    c = TestApp(ma)

    # compute mat 'normals'
    # cross product of spokes is perpendicular to bisector and tangent to sheet
    vec_coplanar = np.cross(ma.D['ma_f1'],ma.D['ma_f2'])
    # now compute this cross product to find a vector in the normal direction of the plane that we want to reconstruct
    ma_n = np.cross(vec_coplanar, ma.D['ma_bisec'])
    ma_n = ma_n / np.linalg.norm(ma_n, axis=1)[:,None]

    layer_s = c.add_layer(LinkedLayer(name='Surface'))
    layer_ma = c.add_layer(LinkedLayer(name='MAT'))
    layer_misc = c.add_layer(LinkedLayer(name='Misc'))

    layer_s.add_data_source(
        name = 'Surface points',
        opts=['splat_disk', 'with_normals'],
        # opts=['splat_disk', 'with_normals', 'fixed_color'],
        points=ma.D['coords'], 
        normals=ma.D['normals'],
        color= (.4,.4,1.)
    )
    layer_s.add_data_source_line(
      name = 'Surface normals',
      coords_start = ma.D['coords'] + ma.D['normals'],
      coords_end = ma.D['coords'],
      color = (1,1,0)
    )

    for v in g.vs():
       ma.D['ma_segment'][v['ma_idx']] = v.index
    # f =ma.D['ma_segment'] != 0
    layer_ma.add_data_source(
        name = 'MAT points',
        opts=['splat_disk', 'with_normals', 'with_intensity'],
        points=ma.D['ma_coords'], 
        normals=ma_n,
        category=ma.D['ma_segment'].astype(np.float),
        colormap='random',
        default_mask=ma.D['ma_segment'] != 0
    )        
    layer_ma.add_data_source_line(
      name = 'Primary spokes',
      coords_start = ma.D['ma_coords'],
      coords_end = np.concatenate([ma.D['coords'],ma.D['coords']])
    )
    layer_ma.add_data_source_line(
      name = 'Secondary spokes',
      coords_start = ma.D['ma_coords'],
      coords_end = np.concatenate([ma.D['coords'],ma.D['coords']])[ma.D['ma_qidx']]
    )
    layer_ma.add_data_source_line(
        name = 'Bisectors',
        coords_start = ma.D['ma_coords'],
        coords_end = ma.D['ma_bisec']+ma.D['ma_coords'],
        color=(.2,.2,1)
    )

    
    layer_misc.add_data_source(
        name = 'Unsegmented mat',
        opts=['splat_point','fixed_color', 'blend'],
        points=ma.D['ma_coords'],
        color=(.6,.6,.6),
        default_mask = ma.D['ma_segment'] == 0
    )
    
    layer_misc.add_data_source(
        name = 'Unsegmented surface',
        opts=['splat_point','fixed_color', 'blend'],
        points=ma.D['coords'],
        color=(.6,.6,.6),
        default_mask = ma.D['ma_segment'][:ma.m] == 0
    )

    flip_rel_start = np.zeros((len(ma.D['seg_link_flip']),3), dtype=np.float32)
    flip_rel_end = np.zeros((len(ma.D['seg_link_flip']),3), dtype=np.float32)
    i=0
    for s,e in ma.D['seg_link_flip'][:,:2]:
        flip_rel_start[i] = ma.g.vs[s]['ma_coords_mean']
        flip_rel_end[i] = ma.g.vs[e]['ma_coords_mean']
        i+=1

    adj_rel_start = np.zeros((len(ma.D['seg_link_adj']),3), dtype=np.float32)
    adj_rel_end = np.zeros((len(ma.D['seg_link_adj']),3), dtype=np.float32)
    i=0
    # f = ma.D['seg_link_adj'][:,2] > min_link_adj
    for s,e in ma.D['seg_link_adj'][:,:2]:
        adj_rel_start[i] = ma.g.vs[s]['ma_coords_mean']
        adj_rel_end[i] = ma.g.vs[e]['ma_coords_mean']
        i+=1
    if len(flip_rel_start)>0:
        layer_misc.add_data_source_line(
            name = 'Flip relations',
            coords_start = flip_rel_start,
            coords_end = flip_rel_end
        )

    if len(adj_rel_start)>0:
        # f = seg_cnts!=1
        layer_misc.add_data_source_line(
            name = 'Adjacency relations',
            coords_start = adj_rel_start,
            coords_end = adj_rel_end,
            color = (0,1,0)
        )

    # c.viewerWindow.center_view(center=np.mean(ma.D['coords'][f_s], axis=0))
    c.run()

if __name__ == '__main__':
    vids = 5
    #box: 4,6,8 (3,10 broken in part)
    #sloped box: 7
    #simple gable: 9
    #exterior: 5
    if len(sys.argv)>1:
        # vids = [int(sys.argv[-1])]
        INFILE = sys.argv[-1]
    else:
    # INFILE = "/Users/ravi/git/mat_util/Random3Dcity/NPY"
        INFILE = "/Users/ravi/git/mat_util/test_cases/sloped_gable/NPY"
    datadict = npy.read(INFILE)
    ma = MAHelper(datadict, origin=True)

    g = ma.D['ma_segment_graph']
    for v in g.vs:
        v['up_angle'] = np.sign(v['ma_bisec_mean'])[2] * np.arccos(np.dot(v['ma_bisec_mean'], [0,0,1] ))

    view(ma, vids)