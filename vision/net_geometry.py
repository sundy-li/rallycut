"""Conservative side-view net mesh estimate from two dark net posts.

One post or the table bbox midpoint is NOT enough to claim net contact. Returned
values are [left_x, left_top, left_bottom, right_x, right_top, right_bottom].
"""


def side_net_region(frame,bounds,method):
    import cv2
    import numpy as np
    if method!='side-color-rim':return []
    height,width=frame.shape[:2]
    left,top,right,bottom=bounds;span=right-left;depth=bottom-top
    if span/depth<4:return []
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    x1=max(0,int(left+span*.25));x2=min(width,int(left+span*.80))
    y1=max(0,int(top-depth*.6));y2=min(height,int(bottom-depth*.08))
    dark=(gray[y1:y2,x1:x2]<95).astype('uint8')*255
    dark=cv2.morphologyEx(dark,cv2.MORPH_OPEN,np.ones((max(9,int(depth*.16)),1),dtype='uint8'))
    lines=cv2.HoughLinesP(dark,1,np.pi/180,threshold=9,minLineLength=max(10,int(depth*.20)),maxLineGap=2)
    strokes=[]
    for values in [] if lines is None else lines[:,0]:
        ax,ay,bx,by=map(int,values)
        if abs(ax-bx)>2:continue
        low,high=min(ay,by)+y1,max(ay,by)+y1
        if low<top-depth*.32 or low>top+depth*.25 or high-low>depth*1.15:continue
        strokes.append(((ax+bx)/2+x1,low,high))
    clusters=[]
    for stroke in sorted(strokes):
        if clusters and stroke[0]-clusters[-1][0][0]<4:clusters[-1].append(stroke)
        else:clusters.append([stroke])
    posts=[]
    for group in clusters:
        lo=min(p[0] for p in group);hi=max(p[0] for p in group)
        low=min(p[1] for p in group);high=max(p[2] for p in group)
        if hi-lo<1 or high-low<depth*.28:continue
        patch=gray[max(0,int(low)):min(height,int(high)+1),max(0,int(lo)):min(width,int(hi)+1)]
        if not patch.size or (patch<95).mean()<.78:continue
        posts.append(((lo+hi)/2,low,high,high-low))
    pairs=[]
    for a in posts:
        for b in posts:
            if not span*.12<b[0]-a[0]<span*.45:continue
            if b[0]<left+span*.55 or a[0]>left+span*.55:continue
            if abs(a[1]-b[1])>depth*.6 or abs(a[2]-b[2])>depth*.7:continue
            pairs.append((a[3]+b[3],a,b))
    if not pairs:return []
    _,a,b=max(pairs)
    return [round(a[0]/width,6),round(a[1]/height,6),round(a[2]/height,6),
            round(b[0]/width,6),round(b[1]/height,6),round(b[2]/height,6)]
