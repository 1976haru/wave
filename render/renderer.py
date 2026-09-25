from __future__ import annotations
import numpy as np
from functools import lru_cache
from time import perf_counter
from pathlib import Path

def parse_color(value):
    value=str(value or "#FFFFFF").lstrip("#")
    if len(value)!=6:value="FFFFFF"
    return np.array([int(value[i:i+2],16) for i in (0,2,4)],np.float32)
@lru_cache(maxsize=256)
def _gradient_lut(start_value,end_value,enabled,count):
    start=parse_color(start_value);end=parse_color(end_value)
    if not enabled:end=start
    return np.linspace(start,end,max(1,count)).astype(np.uint8)
def gradient_colors(template,count):
    return _gradient_lut(str(template.get("gradient_start") or template.get("color","#FFFFFF")),str(template.get("gradient_end") or template.get("color","#FFFFFF")),bool(template.get("gradient")),int(count))
def _geometry(w,h,values,t):
    usable=max(1,int(w*float(t.get("width",.72))));x0=(w-usable)//2;step=usable/max(1,len(values));base={"top":int(h*.18),"center":int(h*.5),"bottom":int(h*.82)}.get(t.get("position","bottom"),int(h*.82));maximum=max(1,int(h*float(t.get("height",.22))));gap=np.clip(float(t.get("gap",.45)),0,.95);width=max(1,int(step*float(t.get("bar_width",1-gap))));return x0,step,base,maximum,width

SIGNATURE_STYLES={"dot_matrix","twin_dot_matrix","dot_line_hybrid","echo_dots","stereo_signature"}

def _hex(value):
    if isinstance(value,(tuple,list,np.ndarray)): return tuple(map(int,value))
    text=str(value).lstrip("#"); return tuple(int(text[i:i+2],16) for i in (0,2,4))

def signature_instances(w,h,state,t):
    """Return batched (x,y,r,color,alpha) dots plus optional line points.

    This is the single deterministic geometry source used by CPU and GPU.
    """
    values=np.asarray(state["values"],np.float32); n=len(values); style=str(t.get("renderer")).lower()
    usable=w*float(t.get("width",.68)); x0=(w-usable)/2+w*float(t.get("x_offset",0)); base=h*float(t.get("baseline_y",.5)); max_rows=max(1,int(t.get("column_limit",8)))
    radius=float(t.get("dot_diameter",4.5))/2; gap=float(t.get("dot_gap",4.0)); pitch=max(radius*2+gap,usable/max(1,n)); xs=x0+(np.arange(n)+.5)*usable/n
    primary=_hex(t.get("color","#FFFFFF")); secondary=_hex(t.get("secondary_color",t.get("color","#FFFFFF"))); accent=_hex(t.get("accent_color",secondary)); highlight=_hex(t.get("highlight_color",accent)); opacity=float(t.get("opacity",1)); dots=[]
    def add_column(x,v,index,color=primary,lean=0.0):
        rows=max(1,min(max_rows,int(np.ceil(float(v)*max_rows))))
        for row in range(rows):
            side=-1 if row%2==0 else 1; level=(row+1)//2 if row else 0
            y=base+side*level*(radius*2+gap)
            dots.append((x+lean*level,y,radius,color,opacity*(.72+.28*(row+1)/rows)))
    if style=="stereo_signature":
        return _stereo_signature_geometry(w,h,state,t,(primary,secondary,accent,highlight))
    if style=="twin_dot_matrix":
        half=n//2; center=w/2; interaction=float(t.get("interaction_strength",.35))*float(state.get("onset",0)); spread=usable*.47
        for i,v in enumerate(values[:half]): add_column(center-spread+(i+.5)*spread/half+interaction*usable*.025,v*(1+.08*float(state.get("mid",0))),i,primary,.10)
        for i,v in enumerate(values[half:]): add_column(center+(i+.5)*spread/max(1,n-half)-interaction*usable*.025,v*(1+.08*float(state.get("bass",0))),i,secondary,-.10)
        if interaction>.08:
            for x in (center-pitch*.65,center+pitch*.65): dots.append((x,base,radius*1.12,accent,min(1,opacity*(.45+interaction))))
    elif style=="dot_line_hybrid":
        smooth=np.convolve(np.pad(values,(2,2),mode="edge"),[.08,.22,.40,.22,.08],mode="valid"); line_y=base-smooth*h*float(t.get("line_height",.06)); threshold=float(t.get("cluster_threshold",.58))
        peaks=(smooth>threshold)&(smooth>=np.roll(smooth,1))&(smooth>=np.roll(smooth,-1))
        for i in np.flatnonzero(peaks): add_column(xs[i],smooth[i]*float(t.get("bloom_amount",.72)),i,secondary)
        return dots,np.column_stack((xs,line_y)).astype(np.float32)
    else:
        for i,v in enumerate(values): add_column(xs[i],v,i,primary)
        if style=="echo_dots" and float(state.get("onset",0))>.18:
            strength=float(state["onset"]); direction=np.where(np.arange(n)%2,-1,1)
            for echo,fade in ((1,.24),(2,.11)):
                for i in np.flatnonzero(values>.62): dots.append((xs[i]+direction[i]*pitch*echo,base,radius*(1-.12*echo),secondary,opacity*fade*strength))
    return dots,None

def _stereo_signature_geometry(w,h,state,t,palette):
    """Nine art-directed stereo signatures sharing one CPU/GPU geometry path."""
    values=np.asarray(state["values"],np.float32); variant=str(t.get("signature_variant","twin_bloom")); p0,p1,p2,p3=palette
    center=w*.5; base=h*float(t.get("baseline_y",.5)); width=w*float(t.get("width",.76)); half_count=max(12,len(values)//2)
    raw=np.resize(values,half_count); smooth=np.convolve(np.pad(raw,(2,2),mode="edge"),[.08,.22,.40,.22,.08],mode="valid")
    # Both halves share musical intent but retain an 8% conversational offset.
    left_raw=np.resize(state.get("left_values",smooth),half_count);right_raw=np.resize(state.get("right_values",smooth),half_count)
    left=np.clip(.82*smooth+.18*np.roll(left_raw,1)*(.82+.18*float(state.get("mid",.5))),0,1);right=np.clip(.78*smooth+.22*np.roll(right_raw,-1)*(.80+.20*float(state.get("bass",.5))),0,1)
    xs=np.linspace(center-width*.48,center-width*.035,half_count); xr=2*center-xs[::-1]; radius=float(t.get("dot_diameter",4.4))/2; gap=float(t.get("dot_gap",3.6)); limit=int(t.get("column_limit",7)); opacity=float(t.get("opacity",.97)); onset=float(state.get("onset",0)); tm=float(state.get("time",0)); dots=[]; lines=[]
    intensity=str(t.get("intensity","NORMAL")).upper()
    intensity_gains={"NORMAL":(1.0,1.0,1.0),"DYNAMIC_SOFT":(1.20,1.15,1.15),"DYNAMIC":(1.30,1.27,1.20)}
    amp_gain,onset_gain,secondary_gain=intensity_gains.get(intensity,intensity_gains["NORMAL"])
    flow_palette=[_hex(c) for c in t.get("flow_palette",["#FF4FA3","#B77CFF","#42D9FF"])]
    flow_period=max(5.0,float(t.get("color_flow_seconds",10.0)))
    def flow_color(position,offset=0):
        phase=((position+tm/flow_period+offset)%1.0)*len(flow_palette);i=int(phase)%len(flow_palette);f=round((phase-i)*2)/2.0;a=np.asarray(flow_palette[i]);b=np.asarray(flow_palette[(i+1)%len(flow_palette)]);return tuple(map(int,np.clip(a*(1-f)+b*f,0,248)))
    def dot(x,y,r,color,alpha=opacity):dots.append((float(x),float(y),float(r),color,float(alpha)))
    def column(x,v,color,outward=1,scale=1):
        rows=max(1,min(limit,int(np.ceil((.18+.82*v)*limit*scale))))
        for j in range(rows):
            side=-1 if j%2==0 else 1; level=(j+1)//2
            dot(x,base+side*level*(2*radius+gap),radius,color,opacity*(.68+.32*(j+1)/rows))
    def line(points,color,alpha=.8,thickness=1,fill=None):lines.append({"points":np.asarray(points,np.float32),"color":color,"alpha":alpha,"thickness":thickness,"fill":fill})
    if variant=="tokyo_chill_signature":
        # One continuous, deliberately non-uniform stereo field shared by all
        # personalities.  The centre is never empty; personality changes the
        # layer balance rather than replacing the brand silhouette.
        personality=str(t.get("personality","DUAL")).upper(); count=max(43,int(t.get("bands",52)))
        rhythm=np.resize(np.asarray([.82,.88,1.34,.86,1.08,.91,1.22],np.float32),count-1)
        positions=np.r_[0,np.cumsum(rhythm)]; positions/=positions[-1]
        xx=center-width*.5+positions*width
        # Each stereo half receives the complete spectrum. This avoids the
        # accidental "bass on the left, treble on the right" imbalance while
        # delayed inputs and small gain differences keep it from being a copy.
        local=np.abs(xx-center)/(width*.5); band_position=np.clip(local*(len(values)-1),0,len(values)-1)
        source=np.interp(band_position,np.arange(len(values)),values)
        left_source=np.interp(band_position,np.arange(len(left_raw)),left_raw)
        right_source=np.interp(band_position,np.arange(len(right_raw)),right_raw)
        stereo=np.where(xx<center,.87*source+.13*np.roll(left_source,1),(.85*source+.15*np.roll(right_source,-2))*.97)
        centre_mix=np.exp(-((xx-center)/(width*.17))**2)
        stereo=np.clip(stereo*(.96+.07*np.sin(np.arange(count)*1.37))+.055*centre_mix,0,1)
        phase=np.linspace(-np.pi,np.pi,count); breathe=np.sin(phase*1.18+tm*.25)
        if personality=="HIS":
            scale=h*.325*amp_gain; curve=np.round((.15+.85*stereo)*8)/8; upper=base-scale*curve*(.58+.24*(np.arange(count)%7==0)); lower=base+scale*np.roll(curve,2)*(.40+.10*(np.arange(count)%5==0)); main_alpha=.88; fill_alpha=.075
        elif personality=="HER":
            scale=h*.285*amp_gain; curve=.16+.84*np.convolve(np.pad(stereo,(2,2),mode="edge"),[.08,.22,.40,.22,.08],mode="valid"); upper=base-scale*curve+breathe*h*.018; lower=base+scale*np.roll(curve,2)*.78-breathe*h*.014; main_alpha=.92; fill_alpha=.115
        else:
            scale=h*.305*amp_gain; pull=.94+.08*np.sin(phase+tm*.38); curve=.16+.84*stereo; upper=base-scale*curve*pull+breathe*h*.010; lower=base+scale*np.roll(curve,1)*(.78+.08*np.cos(phase-tm*.31)); main_alpha=.94; fill_alpha=.10
        # Layer A: connected upper/lower body with slow colour drift.
        line(np.column_stack((xx,upper)),flow_color(.02),main_alpha,2,{"other":np.column_stack((xx,lower)),"color":flow_color(.38),"alpha":fill_alpha*secondary_gain})
        line(np.column_stack((xx,lower)),flow_color(.62),.68 if personality!="HIS" else .76,2 if personality=="HER" else 1)
        bridge=base+breathe*h*.009*(.45+.55*centre_mix)
        line(np.column_stack((xx,bridge)),flow_color(.31),.34+.16*onset*onset_gain,1)
        # Layer B: selective low-mid pillars; dense/sparse rhythm is fixed, not random.
        for i,(x,v) in enumerate(zip(xx,stereo)):
            selected=(i%4 in (0,1) and i%7!=3) or v>.72
            if not selected: continue
            emphasis=1.0+(personality=="HIS")*.22+(personality=="DUAL")*.06
            height=scale*(.15+.52*v)*emphasis*(1.14 if i%9==0 else .72)
            top=base-height; bottom=base+height*(.55 if personality!="HER" else .68)
            color=p3 if v>.78 and i%9==0 else flow_color(i/max(1,count-1)*.84)
            rr=radius*(1.18 if v>.68 else .82)
            dot(x,top,rr,color,.94);dot(x,bottom,rr*.82,color,.70)
            steps=min(limit,max(1,int(height/(radius*2+gap))))
            for j in range(1,steps,2):
                dot(x,base-j*(radius*2+gap),radius*.68,color,.70);dot(x,base+j*(radius*2+gap)*.62,radius*.58,color,.48)
        # Layer C: sparse high shimmer and a short onset travel through centre.
        shimmer=np.abs(stereo-np.roll(stereo,2)); peak_ids=np.flatnonzero((shimmer>.075)&(np.arange(count)%3==0))[:10]
        for i in peak_ids:dot(xx[i],upper[i]-(3+5*shimmer[i]),radius*(.58+.48*stereo[i]),flow_color(i/count+.13),.62)
        pulse=np.clip(onset*onset_gain-.16,0,1)
        if pulse>0:
            direction=-1 if int(tm*3)%2 else 1
            for k in range(-3,4):
                travel=k+direction*pulse*1.4; dot(center+travel*radius*3.4,base+np.sin(k*.72+tm)*h*.009,radius*(.72+.38*pulse-abs(k)*.035),flow_color(.43+k*.025),.38+.45*pulse)
    elif variant=="twin_bloom_v2":
        gap_ratio=max(.055,.115-onset*onset_gain*.035);xl=np.linspace(center-width*.47,center-width*gap_ratio,half_count);xright=2*center-xl[::-1]
        env=np.sin(np.linspace(.08,np.pi-.08,half_count))**.72;left_body=np.clip((.20+.80*left)*env,0,1);right_body=np.clip((.20+.80*right)*env[::-1],0,1);scale=h*.285*amp_gain
        lu=base-left_body*scale;ld=base+np.roll(left_body,1)*scale*.82;ru=base-right_body*scale*.94;rd=base+np.roll(right_body,-1)*scale*.88
        line(np.column_stack((xl,lu)),flow_color(.05),.94,2,{"other":np.column_stack((xl,ld)),"color":flow_color(.26),"alpha":.12*secondary_gain});line(np.column_stack((xright,ru)),flow_color(.58),.94,2,{"other":np.column_stack((xright,rd)),"color":flow_color(.78),"alpha":.12*secondary_gain})
        line(np.column_stack((xl,base-(left_body*.72+np.roll(left_body,2)*.15)*scale*.55)),flow_color(.22),.42*secondary_gain,1);line(np.column_stack((xright,base+(right_body*.68+np.roll(right_body,-2)*.16)*scale*.52)),flow_color(.72),.42*secondary_gain,1)
        for i in range(1,half_count,2):
            dot(xl[i],lu[i],radius*(.82+.35*left_body[i]),flow_color(i/half_count*.42),.94);dot(xright[i],rd[i],radius*(.82+.35*right_body[i]),flow_color(.56+i/half_count*.42),.94)
        pulse=np.clip(onset*onset_gain-.18,0,1)
        if pulse>0:
            for k in range(-2,3):dot(center+k*radius*3,base+np.sin(k*.8+tm)*h*.012,radius*(1.0+pulse*.8-abs(k)*.08),flow_color(.45+k*.025),.45+.48*pulse)
    elif variant=="midnight_grid_v2":
        xx=np.r_[xs,xr];energy=np.r_[left,right];n=len(xx);sky=np.clip(.15+.85*energy*(.62+.38*np.sin(np.arange(n)*1.83+1.2)**2),0,1);scale=h*.32*amp_gain
        tops=[];bottoms=[]
        for i,(x,v) in enumerate(zip(xx,sky)):
            accent=(i%7==0 or v>.72);height=(.22+.78*v)*scale*(1.18 if accent else .68);up=base-height;down=base+height*(.42+.18*((i+1)%3));tops.append(up);bottoms.append(down);color=p3 if accent and v>.76 else flow_color(i/max(1,n-1)*.78)
            thickness=radius*(1.18 if accent else .86);dot(x,up,thickness,color,.96);dot(x,down,thickness*.78,color,.72)
            steps=max(1,int(height/(radius*2+gap)))
            for j in range(1,steps,2):dot(x,base-j*(radius*2+gap),radius*.78,color,.82);dot(x,base+j*(radius*2+gap)*.58,radius*.64,color,.55)
        angular=np.column_stack((xx,np.asarray(tops)*.74+base*.26));line(angular,flow_color(.18),.68,2);line(np.column_stack((xx,np.asarray(bottoms))),flow_color(.62),.30*secondary_gain,1)
        for i in range(3,n,8):dot(xx[i],base+(np.sin(i+tm*.8))*h*.018,radius*.62,flow_color(i/n),.46)
    elif variant=="pearl_bloom_v2":
        allx=np.r_[xs,xr];energy=np.r_[left,right];phase=np.linspace(-np.pi,np.pi,len(allx));breath=.88+.12*np.sin(tm*.72);scale=h*.235*amp_gain;body=np.clip(.18+.82*energy,0,1)
        upper=base-body*scale*breath+np.sin(phase*1.35+tm*.24)*h*.018;lower=base+np.roll(body,2)*scale*.78*breath-np.sin(phase*1.18-tm*.19)*h*.014
        line(np.column_stack((allx,upper)),flow_color(.02),.92,2,{"other":np.column_stack((allx,lower)),"color":flow_color(.33),"alpha":.10*secondary_gain});line(np.column_stack((allx,lower)),flow_color(.58),.74,2)
        echo_up=base+(upper-base)*1.22;echo_down=base+(lower-base)*1.18;line(np.column_stack((allx,echo_up)),flow_color(.28),.28*secondary_gain,1);line(np.column_stack((allx,echo_down)),flow_color(.82),.24*secondary_gain,1)
        peaks=(body>.52)&(body>=np.roll(body,1))&(body>=np.roll(body,-1));indices=np.flatnonzero(peaks)[:8]
        for i in indices:
            size=radius*(1.05+.55*body[i]+.25*onset*onset_gain);dot(allx[i],upper[i],size,flow_color(i/len(allx)),.98);dot(allx[i],lower[i],size*.72,p3,.68)
            if onset>.45:
                for off,fade in ((-1,.38),(1,.38)):dot(allx[i]+off*radius*3.2,upper[i]+off*h*.008,radius*.72,flow_color(i/len(allx)+off*.03),fade)
    elif variant=="twin_bloom":
        for i,(x,v) in enumerate(zip(xs,left)):
            bloom=max(np.exp(-((i-half_count*.22)/(half_count*.13))**2),np.exp(-((i-half_count*.72)/(half_count*.12))**2))
            if i%2==0 or bloom>.62:column(x,v,p0 if i<half_count*.58 else p2,scale=.38+.52*bloom)
            else:dot(x,base,radius*.72,p2,.54)
        for i,(x,v) in enumerate(zip(xr,right)):
            bloom=max(np.exp(-((i-half_count*.22)/(half_count*.13))**2),np.exp(-((i-half_count*.72)/(half_count*.12))**2))
            if i%2==0 or bloom>.62:column(x,v,p1 if i>=half_count*.42 else p2,scale=.38+.52*bloom)
            else:dot(x,base,radius*.72,p2,.54)
        bridge=.10+.32*onset
        for k in range(5):
            angle=(k-2)*.42; dot(center+(k-2)*radius*3,base-np.cos(angle)*bridge*h*.12,radius*(1.08-abs(k-2)*.08),p2,.58+onset*.3)
        y=base-np.sin(np.linspace(0,np.pi,half_count*2))*(.05+.055*onset)*h
        line(np.column_stack((np.r_[xs,xr],y)),p3,.42,1)
    elif variant=="crossfade_conversation":
        allx=np.r_[xs,xr]; energy=np.r_[left,right]
        phase=np.linspace(-np.pi,np.pi,len(allx)); amp=h*(.035+.075*energy)
        upper=base+np.sin(phase+tm*.45)*amp; lower=base-np.sin(phase-tm*.38)*amp
        line(np.column_stack((allx,upper)),p0,.88,2);line(np.column_stack((allx,lower)),p1,.84,2)
        for i in range(2,len(allx)-2,4):
            color=p2 if abs(allx[i]-center)<width*.16 else (p0 if allx[i]<center else p1);dot(allx[i],(upper[i]+lower[i])*.5,radius*(1+.35*energy[i]),color,.84)
    elif variant=="echo_dialogue":
        anchors=(center-width*.25,center+width*.25)
        for side,(anchor,vals,color) in enumerate(((anchors[0],left,p0),(anchors[1],right,p1))):
            for i,v in enumerate(vals[::2]):
                direction=1 if side==0 else -1; x=anchor+direction*i*width*.22/(half_count/2); column(x,v,color,scale=.72)
                if v>.52:
                    for echo,fade in ((1,.34),(2,.17),(3,.08)):dot(x-direction*echo*radius*3.2,base,radius*(1-.1*echo),p2,fade*opacity)
        line([(anchors[0],base),(center-width*.04,base),(center+width*.04,base),(anchors[1],base)],p3,.46,1)
    elif variant=="urban_stereo_pulse":
        for i,(xl,xright,v1,v2) in enumerate(zip(xs,xr,left,right)):
            if i%3==0 or max(v1,v2)>.68:column(xl,v1,p0 if i%6 else p2,scale=.82);column(xright,v2,p1 if i%6 else p2,scale=.82)
            else:dot(xl,base,radius*.72,p1,.58);dot(xright,base,radius*.72,p1,.58)
        line([(xs[0],base),(xr[-1],base)],p3,.48,1)
    elif variant=="midnight_mirror_grid":
        for i,(xl,xright,v) in enumerate(zip(xs,xr,(left+right)*.5)):
            strength=v*(1 if i%4 in (0,1) else .48);column(xl,strength,p0 if i%5 else p2,scale=.9);column(xright,strength,p1 if i%5 else p2,scale=.9)
        edge=h*(.025+.055*onset);line([(xs[0],base-edge),(xs[0],base+edge)],p3,.72,2);line([(xr[-1],base-edge),(xr[-1],base+edge)],p3,.72,2)
    elif variant=="blue_structure_wave":
        allx=np.r_[xs,xr]; e=np.r_[left,right]; angular=np.round(e*5)/5
        y1=base-h*(.025+.072*angular);y2=base+h*(.018+.052*np.roll(angular,2))
        line(np.column_stack((allx,y1)),p0,.92,2);line(np.column_stack((allx,y2)),p1,.70,1)
        for i in range(0,len(allx),5):dot(allx[i],y1[i],radius*(1+.25*e[i]),p2,.88)
    elif variant=="silk_mirror_ribbon":
        allx=np.r_[xs,xr]; e=np.r_[left,right]; wave=np.sin(np.linspace(-np.pi,np.pi,len(allx))+tm*.22)
        upper=base-h*(.028+.062*e)+wave*h*.012;lower=base+h*(.028+.052*np.roll(e,2))-wave*h*.01
        line(np.column_stack((allx,upper)),p0,.76,2,{"other":np.column_stack((allx,lower)),"color":p1,"alpha":.20});line(np.column_stack((allx,lower)),p2,.72,1)
        for i in range(3,len(allx),7):dot(allx[i],upper[i],radius*(1.05+.25*e[i]),p3,.88)
    elif variant=="pearl_stereo_bloom":
        for side,(xx,vv,main) in enumerate(((xs,left,p0),(xr,right,p1))):
            for i,(x,v) in enumerate(zip(xx,vv)):
                if i%2==0 or v>.62:
                    column(x,v,main if i%5 else p2,scale=.74)
                    if v>.55:dot(x,base-(.018+.045*v)*h,radius*1.25,p3,.9)
        line([(xs[0],base),(center-width*.04,base)],p2,.32,1);line([(center+width*.04,base),(xr[-1],base)],p2,.32,1)
    else: # lavender_breathing_line
        allx=np.r_[xs,xr]; e=np.r_[left,right]; breath=.72+.18*np.sin(tm*.75)
        y1=base-h*(.018+.055*e*breath);y2=base+h*(.016+.042*np.roll(e,3)*breath)
        line(np.column_stack((allx,y1)),p0,.88,2);line(np.column_stack((allx,y2)),p1,.64,1)
        for i in np.flatnonzero((e>.52)&(e>=np.roll(e,1))&(e>=np.roll(e,-1))):
            dot(allx[i],y1[i],radius*1.22,p3,.94);dot(2*center-allx[i],base+(base-y1[i])*.72,radius*.88,p2,.58)
    return dots,lines

def build_line_vertices(w,h,values,template,mirror=False):
    """Return a connected miter-style triangle strip in pixel coordinates."""
    values=np.asarray(values,np.float32);x0,step,base,maximum,thickness=_geometry(w,h,values,template);x=x0+(np.arange(len(values))+.5)*step;y=base-values*maximum
    if mirror:y=base+values*maximum
    points=np.column_stack((x,y));colors=gradient_colors(template,len(values)).astype(np.float32)/255
    if len(points)<2:return np.empty((0,5),np.float32)
    tangent=np.empty_like(points);tangent[0]=points[1]-points[0];tangent[-1]=points[-1]-points[-2];tangent[1:-1]=points[2:]-points[:-2];length=np.maximum(np.linalg.norm(tangent,axis=1,keepdims=True),1e-6);tangent/=length;normal=np.column_stack((-tangent[:,1],tangent[:,0]))*(max(1,thickness)/2);left=points+normal;right=points-normal;vertices=np.empty((len(points)*2,5),np.float32);vertices[0::2,:2]=left;vertices[1::2,:2]=right;vertices[0::2,2:]=colors;vertices[1::2,2:]=colors;return vertices

class CPURenderer:
    name="CPU"
    def __init__(self):self.last_profile={}
    def render_rgba(self,w,h,state,template):
        try:import cv2
        except ImportError:return self._numpy(w,h,state,template)
        total_started=perf_counter();values=np.asarray(state["values"],np.float32);setup_started=perf_counter();x0,step,base,maximum,bw=_geometry(w,h,values,template);colors=gradient_colors(template,len(values));setup_elapsed=perf_counter()-setup_started;allocation_started=perf_counter();opacity=int(255*np.clip(float(template.get("opacity",1)),0,1));style=str(template.get("renderer",template.get("style","bars"))).lower();rgb=np.zeros((h,w,3),np.uint8);alpha=np.zeros((h,w),np.uint8);allocation_elapsed=perf_counter()-allocation_started;draw_started=perf_counter();mirror=bool(template.get("mirror"));points=[]
        def bar(x,a,color,down=False):
            y1,y2=(base,min(h-1,base+a)) if down else (max(0,base-a),base);radius=int(min(bw/2,a/2)*np.clip(float(template.get("roundness",0)),0,1));cv2.rectangle(rgb,(x-bw//2,y1),(x+bw//2,y2),tuple(map(int,color)),-1,cv2.LINE_AA);cv2.rectangle(alpha,(x-bw//2,y1),(x+bw//2,y2),opacity,-1,cv2.LINE_AA)
            if radius:cy=y2 if down else y1;cv2.circle(rgb,(x,cy),bw//2,tuple(map(int,color)),-1,cv2.LINE_AA);cv2.circle(alpha,(x,cy),bw//2,opacity,-1,cv2.LINE_AA)
        if style in SIGNATURE_STYLES:
            self._draw_signature(cv2,rgb,alpha,w,h,state,template)
        elif style in {"ribbon","ring","radial"}:
            self._draw_special(cv2, rgb, alpha, values, colors, w, h, base, maximum, bw, template, style, opacity)
        for i,value in enumerate(values if style not in SIGNATURE_STYLES else []):
            amplitude=max(1,int(float(value)*maximum));x=int(x0+(i+.5)*step);points.append((x,base-amplitude))
            if style=="bars":bar(x,amplitude,colors[i]);mirror and bar(x,amplitude,colors[i],True)
            elif style=="dot":
                radius=max(1,bw//2);cv2.circle(rgb,(x,base-amplitude),radius,tuple(map(int,colors[i])),-1,cv2.LINE_AA);cv2.circle(alpha,(x,base-amplitude),radius,opacity,-1,cv2.LINE_AA)
                if mirror:cv2.circle(rgb,(x,base+amplitude),radius,tuple(map(int,colors[i])),-1,cv2.LINE_AA);cv2.circle(alpha,(x,base+amplitude),radius,opacity,-1,cv2.LINE_AA)
        if style=="line" and len(points)>1:
            thickness=max(1,bw)
            for i,(a,b) in enumerate(zip(points[:-1],points[1:])):
                color=tuple(map(int,colors[i]));cv2.line(rgb,a,b,color,thickness,cv2.LINE_AA);cv2.line(alpha,a,b,opacity,thickness,cv2.LINE_AA)
                if mirror:ma=(a[0],2*base-a[1]);mb=(b[0],2*base-b[1]);cv2.line(rgb,ma,mb,color,thickness,cv2.LINE_AA);cv2.line(alpha,ma,mb,opacity,thickness,cv2.LINE_AA)
        draw_elapsed=perf_counter()-draw_started;glow_started=perf_counter()
        if template.get("shadow"):
            shadow=cv2.GaussianBlur(alpha,(0,0),max(1,float(template.get("glow_radius",10))/2));alpha=np.maximum(alpha,(shadow*.25).astype(np.uint8))
        if template.get("glow"):
            radius=max(.1,float(template.get("glow_radius",10)));strength=max(0,float(template.get("glow_strength",.55)));quality=str(template.get("_quality","QUALITY"));default_scale={"PREVIEW":.25,"BALANCED":.5,"QUALITY":1.0}.get(quality,1.0);scale=float(template.get("_glow_scale",default_scale))
            if scale<.999:
                size=(max(1,round(w*scale)),max(1,round(h*scale)));small_a=cv2.resize(alpha,size,interpolation=cv2.INTER_AREA);small_rgb=cv2.resize(rgb,size,interpolation=cv2.INTER_AREA);ga=cv2.resize(cv2.GaussianBlur(small_a,(0,0),max(.1,radius*scale)),(w,h),interpolation=cv2.INTER_LINEAR);gr=cv2.resize(cv2.GaussianBlur(small_rgb,(0,0),max(.1,radius*scale)),(w,h),interpolation=cv2.INTER_LINEAR)
            else:ga=cv2.GaussianBlur(alpha,(0,0),radius);gr=cv2.GaussianBlur(rgb,(0,0),radius)
            alpha=cv2.max(alpha,cv2.convertScaleAbs(ga,alpha=strength));rgb=cv2.addWeighted(rgb,1.0,gr,strength,0)
        glow_elapsed=perf_counter()-glow_started;final_started=perf_counter();rgb[alpha==0]=0;result=np.dstack((rgb,alpha));final_elapsed=perf_counter()-final_started;self.last_profile={"setup_ms":setup_elapsed*1000,"allocation_ms":allocation_elapsed*1000,"draw_ms":draw_elapsed*1000,"glow_ms":glow_elapsed*1000,"final_copy_ms":final_elapsed*1000,"total_ms":(perf_counter()-total_started)*1000};return result
    def _draw_signature(self,cv2,rgb,alpha,w,h,state,t):
        dots,line=signature_instances(w,h,state,t); halo=float(t.get("halo_alpha",.14)); halo_scale=float(t.get("halo_scale",1.75))
        # Two batched contour calls (halo/core), independent of dot count.
        def contours(scale):
            if not dots:return []
            centers=np.asarray([(d[0],d[1]) for d in dots],np.float32)[:,None,:];radii=np.maximum(1,np.asarray([d[2] for d in dots],np.float32)*scale)[:,None,None];angles=np.linspace(0,2*np.pi,12,endpoint=False,dtype=np.float32);unit=np.column_stack((np.cos(angles),np.sin(angles)))[None,:,:]
            return list(np.rint(centers+radii*unit).astype(np.int32))
        if dots:
            # Palette groups preserve colour identity while retaining batching.
            for color in {d[3] for d in dots}:
                selected=[d for d in dots if d[3]==color]
                original=dots; dots=selected
                if halo>0:
                    cv2.fillPoly(rgb,contours(halo_scale),color,lineType=cv2.LINE_AA); cv2.fillPoly(alpha,contours(halo_scale),int(255*halo),lineType=cv2.LINE_AA)
                cv2.fillPoly(rgb,contours(1),color,lineType=cv2.LINE_AA); cv2.fillPoly(alpha,contours(1),int(255*max(d[4] for d in selected)),lineType=cv2.LINE_AA)
                dots=original
        if line is not None:
            layers=line if isinstance(line,list) else [{"points":line,"color":_hex(t.get("line_color",t.get("color","#FFFFFF"))),"alpha":float(t.get("baseline_strength",.72)),"thickness":int(t.get("line_thickness",1))}]
            for layer in layers:
                points=layer["points"]; color=layer["color"]; strength=float(layer.get("alpha",.72));thickness=max(1,int(layer.get("thickness",1)));fill=layer.get("fill")
                if fill:
                    other=fill["other"];poly=np.vstack((points,other[::-1])).astype(np.int32);fill_strength=float(fill.get("alpha",.18));fill_color=tuple(int(c*fill_strength) for c in fill.get("color",color));fill_alpha=int(255*fill_strength);cv2.fillPoly(rgb,[poly],fill_color,lineType=cv2.LINE_AA);cv2.fillPoly(alpha,[poly],fill_alpha,lineType=cv2.LINE_AA)
                if len(points)>1:
                    pts=points.astype(np.int32).reshape((-1,1,2));cv2.polylines(rgb,[pts],False,color,thickness,cv2.LINE_AA);cv2.polylines(alpha,[pts],False,int(255*strength),thickness,cv2.LINE_AA)
    def _draw_special(self, cv2, rgb, alpha, values, colors, w, h, base, maximum, bw, template, style, opacity):
        n=len(values); center=(w//2,h//2); mirror=bool(template.get("mirror")); thickness=max(1,int(template.get("bar_width",.55)*max(2,bw)))
        if style=="ribbon":
            x0,step,_,_,_= _geometry(w,h,values,template); xs=np.linspace(x0+step*.5,x0+step*(n-.5),n); smooth=np.convolve(np.r_[values[0],values,values[-1]],[.2,.6,.2],mode="same")[1:-1]; ys=base-smooth*maximum
            pts=np.column_stack((xs,ys)).astype(np.float32); tangent=np.gradient(pts,axis=0); tangent/=np.maximum(np.linalg.norm(tangent,axis=1,keepdims=True),1e-6); normal=np.column_stack((-tangent[:,1],tangent[:,0])); half=np.maximum(2.0,thickness*(.7+smooth*.8)); top=(pts+normal*half[:,None]).astype(np.int32); bottom=(pts-normal*half[:,None]).astype(np.int32); poly=np.vstack([top,bottom[::-1]]); cv2.fillPoly(rgb,[poly],(220,235,255)); cv2.fillPoly(alpha,[poly],opacity); cv2.polylines(rgb,[top.reshape((-1,1,2)),bottom.reshape((-1,1,2))],False,(255,255,255),1,cv2.LINE_AA)
            if mirror:
                mp=poly.copy(); mp[:,1]=2*base-mp[:,1]; cv2.fillPoly(rgb,[mp],(220,235,255)); cv2.fillPoly(alpha,[mp],opacity)
            return
        if style in {"ring","radial"}:
            count=max(8,n); angles=np.linspace(-np.pi/2,1.5*np.pi,count,endpoint=False); vals=np.resize(values,count); cx,cy=center; inner=float(template.get("inner_radius",.18 if style=="ring" else .12))*min(w,h); scale=float(template.get("radial_scale",.32))*min(w,h)
            for i,(ang,val) in enumerate(zip(angles,vals)):
                r0=inner; r1=inner+max(2,float(val)*scale); x0=int(cx+np.cos(ang)*r0); y0=int(cy+np.sin(ang)*r0); x1=int(cx+np.cos(ang)*r1); y1=int(cy+np.sin(ang)*r1); col=tuple(map(int,colors[i%len(colors)])); cv2.line(rgb,(x0,y0),(x1,y1),col,thickness,cv2.LINE_AA); cv2.line(alpha,(x0,y0),(x1,y1),opacity,thickness,cv2.LINE_AA)
            if style=="ring": cv2.circle(rgb,(cx,cy),max(1,int(inner)),(30,35,45),max(1,thickness//2),cv2.LINE_AA)
    def _numpy(self,w,h,state,t):
        out=np.zeros((h,w,4),np.uint8);values=np.asarray(state["values"]);x0,step,base,maximum,bw=_geometry(w,h,values,t);colors=gradient_colors(t,len(values));opacity=int(255*float(t.get("opacity",1)))
        for i,v in enumerate(values):
            a=max(1,int(v*maximum));x=int(x0+(i+.5)*step);xa,xb=max(0,x-bw//2),min(w,x+bw//2+1);out[max(0,base-a):base+1,xa:xb,:3]=colors[i];out[max(0,base-a):base+1,xa:xb,3]=opacity
            if t.get("mirror"):out[base:min(h,base+a),xa:xb,:3]=colors[i];out[base:min(h,base+a),xa:xb,3]=opacity
        return out

class GPUBarRenderer:
    """ModernGL waveform renderer with connected lines and two-pass GPU glow."""
    name="GPU"
    def __init__(self):
        import moderngl
        self.gl=moderngl;self.ctx=moderngl.create_standalone_context(require=330);self.quad=self.ctx.buffer(np.array([[0,0],[1,0],[0,1],[1,1]],"f4").tobytes());self.screen=self.ctx.buffer(np.array([[-1,-1],[1,-1],[-1,1],[1,1]],"f4").tobytes())
        self.shape_program=self.ctx.program(vertex_shader='''#version 330
in vec2 corner;in vec4 rect;in vec3 instance_color;uniform vec2 viewport;out vec2 uv;out vec3 vcolor;
void main(){uv=corner;vcolor=instance_color;vec2 p=rect.xy+(corner-.5)*rect.zw;gl_Position=vec4(p/viewport*2.0-1.0,0,1);}''',fragment_shader='''#version 330
in vec2 uv;in vec3 vcolor;uniform float opacity;uniform int shape;uniform float roundness;out vec4 frag;
void main(){float a=opacity;if(shape==1)a*=smoothstep(.52,.44,length(uv-.5));else if(roundness>0.0){vec2 q=abs(uv-.5)-vec2(.5-roundness*.45);a*=1.0-smoothstep(roundness*.44,roundness*.5,length(max(q,0.0)));}frag=vec4(vcolor,a);}''')
        self.special_program=self.ctx.program(vertex_shader="""#version 330
in vec2 position;in vec3 vertex_color;uniform vec2 viewport;out vec3 vcolor;void main(){vcolor=vertex_color;vec2 p=vec2(position.x,viewport.y-position.y);gl_Position=vec4(p/viewport*2.0-1.0,0,1);}""",fragment_shader="""#version 330
in vec3 vcolor;uniform float opacity;out vec4 frag;void main(){frag=vec4(vcolor,opacity);}""")
        self.line_program=self.ctx.program(vertex_shader='''#version 330
in vec2 position;in vec3 vertex_color;uniform vec2 viewport;out vec3 vcolor;
void main(){vcolor=vertex_color;vec2 p=vec2(position.x,viewport.y-position.y);gl_Position=vec4(p/viewport*2.0-1.0,0,1);}''',fragment_shader='''#version 330
in vec3 vcolor;uniform float opacity;out vec4 frag;void main(){frag=vec4(vcolor,opacity);}''')
        self.blur_program=self.ctx.program(vertex_shader='''#version 330
in vec2 position;out vec2 uv;void main(){uv=position*.5+.5;gl_Position=vec4(position,0,1);}''',fragment_shader='''#version 330
uniform sampler2D source;uniform vec2 direction;in vec2 uv;out vec4 frag;
void main(){vec4 c=texture(source,uv)*.227027;c+=texture(source,uv+direction*1.384615)*.316216;c+=texture(source,uv-direction*1.384615)*.316216;c+=texture(source,uv+direction*3.230769)*.070270;c+=texture(source,uv-direction*3.230769)*.070270;frag=c;}''')
        self.composite_program=self.ctx.program(vertex_shader='''#version 330
in vec2 position;out vec2 uv;void main(){uv=position*.5+.5;gl_Position=vec4(position,0,1);}''',fragment_shader='''#version 330
uniform sampler2D original;uniform sampler2D glow;uniform float strength;in vec2 uv;out vec4 frag;
void main(){vec4 a=texture(original,uv);vec4 g=texture(glow,uv)*strength;frag=vec4(min(a.rgb+g.rgb,vec3(1)),max(a.a,g.a));}''')
        self.blur_vao=self.ctx.simple_vertex_array(self.blur_program,self.screen,"position");self.composite_vao=self.ctx.simple_vertex_array(self.composite_program,self.screen,"position")
        self._instance_capacity=4096; self._rect_buffer=self.ctx.buffer(reserve=self._instance_capacity*16,dynamic=True); self._color_buffer=self.ctx.buffer(reserve=self._instance_capacity*12,dynamic=True)
    def available(self):return True
    def _draw_shapes(self,w,h,values,t):
        x0,step,base,maximum,bw=_geometry(w,h,values,t);mirror=bool(t.get("mirror"));rects=[];colors=[]
        for i,v in enumerate(values):
            amplitude=max(1,float(v)*maximum);cx=x0+(i+.5)*step;style=t.get("renderer","bars")
            if style=="dot":rects.append((cx,h-(base-amplitude),bw,bw))
            else:rects.append((cx,h-base+amplitude/2,bw,amplitude))
            colors.append(gradient_colors(t,len(values))[i]/255)
            if mirror:
                if style=="dot":rects.append((cx,h-(base+amplitude),bw,bw))
                else:rects.append((cx,h-base-amplitude/2,bw,amplitude))
                colors.append(gradient_colors(t,len(values))[i]/255)
        rb=self.ctx.buffer(np.asarray(rects,"f4").tobytes());cb=self.ctx.buffer(np.asarray(colors,"f4").tobytes());vao=self.ctx.vertex_array(self.shape_program,[(self.quad,"2f","corner"),(rb,"4f/i","rect"),(cb,"3f/i","instance_color")]);self.shape_program["viewport"].value=(w,h);self.shape_program["opacity"].value=float(t.get("opacity",1));self.shape_program["shape"].value=1 if t.get("renderer")=="dot" else 0;self.shape_program["roundness"].value=float(t.get("roundness",0));vao.render(self.gl.TRIANGLE_STRIP,instances=len(rects));vao.release();rb.release();cb.release()
    def _draw_signature(self,w,h,state,t):
        dots,line=signature_instances(w,h,state,t); rects=[]; colors=[]
        halo=float(t.get("halo_alpha",.14)); hs=float(t.get("halo_scale",1.75))
        for scale,alpha_scale in ((hs,halo),(1.0,1.0)):
            if alpha_scale<=0: continue
            for x,y,r,color,a in dots:
                rects.append((x,h-y,2*r*scale,2*r*scale)); colors.append(np.asarray(color,np.float32)/255*min(1,a*alpha_scale))
        if rects:
            count=len(rects); rb=np.asarray(rects,"f4"); cb=np.asarray(colors,"f4")
            if count>self._instance_capacity: raise RuntimeError("signature instance capacity exceeded")
            self._rect_buffer.write(rb.tobytes()); self._color_buffer.write(cb.tobytes()); vao=self.ctx.vertex_array(self.shape_program,[(self.quad,"2f","corner"),(self._rect_buffer,"4f/i","rect"),(self._color_buffer,"3f/i","instance_color")]); self.shape_program["viewport"].value=(w,h); self.shape_program["opacity"].value=1.0; self.shape_program["shape"].value=1; self.shape_program["roundness"].value=1.0; vao.render(self.gl.TRIANGLE_STRIP,instances=count); vao.release()
        if line is not None:
            layers=line if isinstance(line,list) else [{"points":line,"color":_hex(t.get("line_color",t.get("color","#FFFFFF"))),"alpha":float(t.get("baseline_strength",.72))}]
            for layer in layers:
                points=layer["points"]
                if len(points)<2:continue
                color=np.asarray(layer["color"],np.float32)/255;verts=np.column_stack((points,np.tile(color,(len(points),1)))).astype("f4");buf=self.ctx.buffer(verts.tobytes());vao=self.ctx.vertex_array(self.special_program,[(buf,"2f 3f","position","vertex_color")]);self.special_program["viewport"].value=(w,h);self.special_program["opacity"].value=float(layer.get("alpha",.72));vao.render(self.gl.LINE_STRIP);vao.release();buf.release()
    def _draw_line(self,w,h,values,t):
        for mirror in ([False,True] if t.get("mirror") else [False]):
            vertices=build_line_vertices(w,h,values,t,mirror)
            if not len(vertices):continue
            buffer=self.ctx.buffer(vertices.tobytes());vao=self.ctx.vertex_array(self.line_program,[(buffer,"2f 3f","position","vertex_color")]);self.line_program["viewport"].value=(w,h);self.line_program["opacity"].value=float(t.get("opacity",1));vao.render(self.gl.TRIANGLE_STRIP);vao.release();buffer.release()
    def _special_vertices(self,w,h,values,t,style):
        x0,step,base,maximum,bw=_geometry(w,h,values,t); colors=gradient_colors(t,len(values)).astype(np.float32)/255; n=len(values)
        if style=="ribbon":
            xs=np.linspace(x0+step*.5,x0+step*(n-.5),n); smooth=np.convolve(np.r_[values[0],values,values[-1]],[.2,.6,.2],mode="same")[1:-1]; ys=base-smooth*maximum; pts=np.column_stack((xs,ys)).astype(np.float32); tangent=np.gradient(pts,axis=0); tangent/=np.maximum(np.linalg.norm(tangent,axis=1,keepdims=True),1e-6); normal=np.column_stack((-tangent[:,1],tangent[:,0])); half=np.maximum(2.0,float(t.get("bar_width",.55))*max(2,bw)*(.7+smooth*.8)); verts=[]
            for i in range(n): verts.extend([(pts[i]+normal[i]*half[i]).tolist()+colors[i].tolist(),(pts[i]-normal[i]*half[i]).tolist()+colors[i].tolist()])
            return np.asarray(verts,"f4"),self.gl.TRIANGLE_STRIP
        center=np.array([w/2,h/2],np.float32); count=max(8,n); angles=np.linspace(-np.pi/2,1.5*np.pi,count,endpoint=False); vals=np.resize(values,count); inner=float(t.get("inner_radius",.18 if style=="ring" else .10))*min(w,h); scale=float(t.get("radial_scale",.32))*min(w,h)
        if style=="radial":
            radii=inner+vals*scale; pts=np.column_stack((center[0]+np.cos(angles)*radii,center[1]+np.sin(angles)*radii)); cols=np.resize(colors,(count,3)); return np.column_stack((pts,cols)).astype("f4"),self.gl.LINE_STRIP
        verts=[]
        for i,(ang,val) in enumerate(zip(angles,vals)):
            p0=center+np.array([np.cos(ang)*inner,np.sin(ang)*inner]); p1=center+np.array([np.cos(ang)*(inner+val*scale),np.sin(ang)*(inner+val*scale)]); tangent=np.array([-np.sin(ang),np.cos(ang)]); half=max(1,float(t.get("bar_width",.55))*max(2,bw)/2); c=colors[i%len(colors)]; verts.extend([(p0+tangent*half).tolist()+c.tolist(),(p0-tangent*half).tolist()+c.tolist(),(p1+tangent*half).tolist()+c.tolist(),(p1-tangent*half).tolist()+c.tolist()])
        return np.asarray(verts,"f4"),self.gl.TRIANGLE_STRIP
    def _draw_special_gpu(self,w,h,values,t):
        vertices,mode=self._special_vertices(w,h,values,t,str(t.get("renderer")).lower()); buf=self.ctx.buffer(vertices.tobytes()); vao=self.ctx.vertex_array(self.special_program,[(buf,"2f 3f","position","vertex_color")]); self.special_program["viewport"].value=(w,h); self.special_program["opacity"].value=float(t.get("opacity",1)); vao.render(mode); vao.release(); buf.release()
    def _gpu_glow(self,w,h,original,strength,radius):
        textures=[self.ctx.texture((w,h),4,dtype="f1") for _ in range(3)];fbos=[self.ctx.framebuffer([tex]) for tex in textures];original.use(0);self.blur_program["source"].value=0;fbos[0].use();self.blur_program["direction"].value=(max(1,radius)/w,0);self.blur_vao.render(self.gl.TRIANGLE_STRIP);textures[0].use(0);fbos[1].use();self.blur_program["direction"].value=(0,max(1,radius)/h);self.blur_vao.render(self.gl.TRIANGLE_STRIP);original.use(0);textures[1].use(1);fbos[2].use();self.composite_program["original"].value=0;self.composite_program["glow"].value=1;self.composite_program["strength"].value=float(strength);self.composite_vao.render(self.gl.TRIANGLE_STRIP);return textures,fbos,textures[2]
    def render_rgba(self,w,h,state,t):
        values=np.asarray(state["values"],"f4");base=self.ctx.texture((w,h),4,dtype="f1");base.filter=(self.gl.LINEAR,self.gl.LINEAR);fbo=self.ctx.framebuffer([base]);fbo.use();self.ctx.clear(0,0,0,0);self.ctx.enable(self.gl.BLEND);self.ctx.blend_func=(self.gl.SRC_ALPHA,self.gl.ONE_MINUS_SRC_ALPHA)
        if str(t.get("renderer")).lower() in SIGNATURE_STYLES:self._draw_signature(w,h,state,t)
        elif t.get("renderer")=="line":self._draw_line(w,h,values,t)
        elif str(t.get("renderer")).lower() in {"ribbon","ring","radial"}: self._draw_special_gpu(w,h,values,t)
        else:self._draw_shapes(w,h,values,t)
        resources=[];output=base
        if t.get("glow"):
            textures,fbos,output=self._gpu_glow(w,h,base,float(t.get("glow_strength",.55)),float(t.get("glow_radius",10)));resources=(textures,fbos)
        data=np.frombuffer(output.read(alignment=1),np.uint8).reshape(h,w,4);fbo.release();base.release()
        if resources:
            for item in resources[1]:item.release()
            for item in resources[0]:item.release()
        return np.flipud(data).copy()

class AutoRenderer:
    name="GPU"
    def __init__(self):
        self.cpu=CPURenderer()
        try:self.active=GPUBarRenderer()
        except Exception:self.active=self.cpu;self.name="CPU"
    def render_rgba(self,w,h,state,template):
        try:return self.active.render_rgba(w,h,state,template)
        except Exception:
            self.active=self.cpu;self.name="CPU";return self.cpu.render_rgba(w,h,state,template)

class AdaptiveRenderer:
    """AUTO renderer: micro-benchmarks CPU/GPU for the requested geometry and caches the choice."""
    def __init__(self, template=None):
        self.template=dict(template or {"renderer":"bars","bands":64}); self.cpu=CPURenderer(); self.active=self.cpu; self.name="CPU"; self.profile={"renderer":str(self.template.get("renderer","bars"))}
        try:
            gpu=GPUBarRenderer(); values=np.abs(np.sin(np.linspace(0,9,64))).astype("f4")*.55+.2; state={"values":values}
            import time
            def measure(renderer):
                start=time.perf_counter(); [renderer.render_rgba(320,180,state,self.template) for _ in range(2)]; return (time.perf_counter()-start)/2
            cpu_ms=measure(self.cpu); gpu_ms=measure(gpu); self.profile.update({"cpu_ms":cpu_ms*1000,"gpu_ms":gpu_ms*1000});
            if gpu_ms <= cpu_ms*1.15: self.active=gpu; self.name="GPU"
        except Exception as exc:
            self.profile["gpu_error"]=repr(exc)
        self._save_profile()
    def _save_profile(self):
        try:
            path=Path("cache/renderer_profile.json"); path.parent.mkdir(exist_ok=True); path.write_text(__import__("json").dumps(self.profile,indent=2),encoding="utf-8")
        except Exception: pass
    def render_rgba(self,w,h,state,template):
        try:return self.active.render_rgba(w,h,state,template)
        except Exception:
            self.active=self.cpu; self.name="CPU"; return self.cpu.render_rgba(w,h,state,template)

class RendererFactory:
    @staticmethod
    def create(choice="AUTO",template=None):
        choice=choice.upper()
        if choice=="AUTO":return AdaptiveRenderer(template)
        if choice=="GPU":return GPUBarRenderer()
        return CPURenderer()







