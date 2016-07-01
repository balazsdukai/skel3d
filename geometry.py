import numpy as np
from graph import *
import random
from geom3d import *

from sklearn.cluster import KMeans

def ransac_plane_fit(point_array, point_indices, threshold=0.05, n_planes=2, max_iterations=10):
    # choose 3 random points

    idx = list(point_indices)

    # we are searching for n_planes solutions, but we may only find a lower number of planes    
    solutions = []
    for i in range(n_planes):
        if len(idx) < 3:
            break
        iteration_cnt = 0
        candidate_solutions = []
        while iteration_cnt < max_iterations:
            random.shuffle(idx)
            seeds = idx[:3]
            # import ipdb; ipdb.set_trace()
            try: 
                candidate_plane = Plane( [Point( point_array[pi]) for pi in seeds] )
            except ValueError:
                continue

            inliers = seeds
            for pi in idx[3:]:
                d = candidate_plane.distance_to( Point(point_array[pi]) )
                if d < threshold:
                    inliers.append(pi)
            candidate_solutions.append( (candidate_plane, inliers) )

            iteration_cnt+=1
        # determine best Plane
        candidate_solutions.sort(key=lambda tup: len(tup[1]), reverse=True)
        plane, inliers = candidate_solutions[0]

        idx = list(set(idx) - set(inliers))
        solutions.append(plane)
    
    return solutions

def derive_tetra(plane1, plane2, point_indices, ma):
    line = plane1.intersection(plane2)

    line_range = []
    for c in ma.D['ma_coords'][point_indices]:
        p = Point(c)
        s = np.inner(line.t,p.r - line.r)
        line_range.append(s)
    s_mi, s_ma = min(line_range), max(line_range)
    v0,v1 = line.t*s_mi+line.r, line.t*s_ma+line.r

    pi_maxr =  np.argmax(ma.D['ma_radii'][point_indices])
    p_maxr = ma.D['ma_coords'][point_indices][pi_maxr]

    v2 = plane1.project(Point(p_maxr)).r
    v3 = plane2.project(Point(p_maxr)).r

    # center v2,v3 nicely to be halfway across v0,v1
    s = np.inner(line.t,v2 - line.r)
    move_to_center = (s_mi + (s_ma-s_mi)/2 - s)*line.t
    v2 += move_to_center
    v3 += move_to_center

    return np.array([v0, v1, v2, v3], dtype=np.float32)

# def get_graph_library():
#     graph_library = {}
#     g = igraph.Graph()
#     g.add_vertices(4)
#     g.add_edges([(0,1), (1,2), (2,3), (3,0), (0,2)])
#     graph_library['flatcube_top'] = g

#     return graph_library

def gf_flatcube_top(master_graph, mapping, ma, ground_level=0):
    """compute cube geometry for matched graph based on the mapping with library graph
         v0
        /|\
       / | \
     v1  |  v3
       \ | /
        \|/
         v2
        each vertex is a sheet
        each sheet contributes to the top plane
        each sheet has one other side plane
    """
    g_flatcube_top = get_graph_library()['flatcube_top']
    g = master_graph
    v0, v1, v2, v3 = mapping
    
    # for each sheet find two sets of surface points, each corresponding to a distict plane. Use cross-product of spoke vectors with avg bisector of sheet to decide
    pointsets = {}
    coord_idx = []
    for vid in mapping:
        # obtain set of surface points (regardless of what is in/out)
        bisec_mean = g.vs[vid]['ma_bisec_mean']
        ma_idx = g.vs[vid]['ma_idx']
        s_idx = np.mod(ma_idx, ma.m)

        # collect normals and flip outward if necessary
        normals_1 = []
        normals_2 = []
        for ma_id, s_id in zip(ma_idx, s_idx):
            c = ma.D['ma_coords'][ma_id]
            # b = ma.D['ma_bisec'][ma_id]
            n1 = ma.D['normals'][s_id]
            f1 = c-ma.D['coords'][s_id]
            if np.inner(f1,n1) > 0:
                n1*=-1
            n2 = ma.D['normals'][ma.D['ma_qidx'][ma_id]]
            f2 = c-ma.D['coords'][ma.D['ma_qidx'][ma_id]]
            if np.inner(f2,n2) > 0:
                n2*=-1
            normals_1.append(f1/np.linalg.norm(f1))
            normals_2.append(f2/np.linalg.norm(f2))

        idx = np.concatenate([s_idx, ma.D['ma_qidx'][ma_idx]])

        km = KMeans(n_clusters = 2)
        labels = km.fit_predict(normals_1+normals_2)
        pts_0 = set(idx[labels==0])
        pts_1 = set(idx[labels==1])
        coord_idx.extend(idx)
        
        # print labels
        pointsets[vid] = [x/np.linalg.norm(x) for x in km.cluster_centers_], (pts_0, pts_1)
        # return ma_idx, normals, labels
            
    # return pointsets
    # aggregate points for common planes based on graph topology

    ## top Plane
    def angle(a, b):
        a = a/np.linalg.norm(a)
        b = b/np.linalg.norm(b)
        return np.arccos(np.inner(a, b))

    # print [len( x[1][0] | x[1][1] ) for x in pointsets.values()]
    
    c0,c2 = pointsets[v0][0], pointsets[v2][0]
    angle_thres = 20
    print "c0[0], c2[0]",
    print math.degrees(angle(c0[0], c2[0]))
    print "c0[0], c2[1]",
    print math.degrees(angle(c0[0], c2[1]))
    print "c0[1], c2[0]",
    print math.degrees(angle(c0[1], c2[0]))
    print "c0[1], c2[1]",
    print math.degrees(angle(c0[1], c2[1]))
    if angle(c0[0], c2[0]) < math.radians(angle_thres):
        up = c0[0]
        plane_top_pts = pointsets[v0][1][0] | pointsets[v2][1][0]  
        plane_0_pts = pointsets[v0][1][1]
        plane_2_pts = pointsets[v2][1][1]
    elif angle(c0[0], c2[1]) < math.radians(angle_thres):
        up = c0[0]
        plane_top_pts = pointsets[v0][1][0] | pointsets[v2][1][1]  
        plane_0_pts = pointsets[v0][1][1]
        plane_2_pts = pointsets[v2][1][0]
    elif angle(c0[1], c2[0]) < math.radians(angle_thres):
        up = c0[1]
        plane_top_pts = pointsets[v0][1][1] | pointsets[v2][1][0]  
        plane_0_pts = pointsets[v0][1][0]
        plane_2_pts = pointsets[v2][1][1]
    else:
        up = c0[1]
        plane_top_pts = pointsets[v0][1][1] | pointsets[v2][1][1]  
        plane_0_pts = pointsets[v0][1][0]
        plane_2_pts = pointsets[v2][1][0]

    if angle(up, pointsets[v1][0][0]) < math.radians(angle_thres):
        plane_top_pts |= pointsets[v1][1][0]
        plane_1_pts = pointsets[v1][1][1]
    else:
        plane_top_pts |= pointsets[v1][1][1]
        plane_1_pts = pointsets[v1][1][0]
        

    if angle(up, pointsets[v3][0][0]) < math.radians(angle_thres):
        plane_top_pts |= pointsets[v3][1][0]
        plane_3_pts = pointsets[v3][1][1]
    else:
        plane_top_pts |= pointsets[v3][1][1]
        plane_3_pts = pointsets[v3][1][0] 

    # compute for each aggregate set of surface points a Plane
    plane_top = Plane( [Point( ma.D['coords'][pi]) for pi in plane_top_pts] )
    plane_0 = Plane( [Point( ma.D['coords'][pi]) for pi in plane_0_pts] )
    plane_1 = Plane( [Point( ma.D['coords'][pi]) for pi in plane_1_pts] )
    plane_2 = Plane( [Point( ma.D['coords'][pi]) for pi in plane_2_pts] )
    plane_3 = Plane( [Point( ma.D['coords'][pi]) for pi in plane_3_pts] )

    # intersect planes using graph topology, compute the vertices of the roof plane, extrude down to z=0
    line_0 = plane_top.intersection(plane_0)
    line_1 = plane_top.intersection(plane_1)
    line_2 = plane_top.intersection(plane_2)
    line_3 = plane_top.intersection(plane_3)

    line_01 = plane_0.intersection(plane_1)
    line_12 = plane_1.intersection(plane_2)
    line_23 = plane_2.intersection(plane_3)
    line_30 = plane_3.intersection(plane_0)
    

    def line_intersect(l1,l2):
        # assuming there is an intersection and the lines are not parallel
        l2m = (l1.t[0] * (l2.r[1]-l1.r[1]) + l1.t[1]*l1.r[0] - l2.r[0]*l1.t[1]) / (l2.t[0]*l1.t[1] - l1.t[0]*l2.t[1])
        return l2.r + l2m*l2.t

    q0 = line_intersect(line_0, line_01)
    q1 = line_intersect(line_1, line_12)
    q2 = line_intersect(line_2, line_23)
    q3 = line_intersect(line_3, line_30)

    ground_level = ma.D['coords'][coord_idx][:,2].min()
    q0_ = q0.copy()
    q0_[2] = ground_level
    q1_ = q1.copy()
    q1_[2] = ground_level
    q2_ = q2.copy()
    q2_[2] = ground_level
    q3_ = q3.copy()
    q3_[2] = ground_level
    # print q0
    # print q1
    # print q2
    # print q3

    # coords = np.empty((6,3), dtype=np.float32)
    normals = np.empty((30,3), dtype=np.float32)

    coords = np.array([     q0,q1,q2, q0,q2,q3, 
                            q0,q0_,q1_, q0,q1_,q1, 
                            q1,q1_,q2, q2,q1_,q2_,
                            q2,q2_,q3_, q3,q2,q3_,
                            q0,q3,q3_, q0,q3_,q0_ ], dtype=np.float32)
    normals[0:6] = plane_top.n
    normals[6:12] = plane_0.n
    normals[12:18] = plane_1.n
    normals[18:24] = plane_2.n
    normals[24:30] = plane_3.n

    return coords, normals, (plane_top_pts, plane_0_pts, plane_1_pts, plane_2_pts, plane_3_pts)