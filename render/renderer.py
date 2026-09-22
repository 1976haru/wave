from __future__ import annotations
import numpy as np

def parse_color(value):
    value=str(value or "#FFFFFF").lstrip("#");
    if len(value)!=6: value="FFFFFF"
    return np.array([int(value[i:i+2],16) for i in (0,2,4)],np.float32)

def gradient_colors(template,count):
    start=parse_color(template.get("gradient_start") or template.get("color","#FFFFFF")); end=parse_color(template.get("gradient_end") or template.get("color","#FFFFFF")); enabled=bool(template.get("gradient")) or template.get("gradient_start") is not None
    if not enabled: end=start
    return np.linspace(start,end,max(1,count)).astype(np.uint8)

def _geometry(w,h,values,t):
    usable=max(1,int(w*float(t.get("width",.72)))); x0=(w-usable)//2; step=usable/max(1,len(values)); base={"top":int(h*.18),"center":int(h*.5),"bottom":int(h*.82)}.get(t.get("position","bottom"),int(h*.82)); maximum=max(1,int(h*float(t.get("height",.22)))); gap=np.clip(float(t.get("gap",.45)),0,.95); width=max(1,int(step*float(t.get("bar_width",1-gap)))); return x0,step,base,maximum,width

class CPURenderer:
    name="CPU"
    def render_rgba(self,w,h,state,template):
        try: import cv2
        except ImportError: return self._numpy(w,h,state,template)
        values=np.asarray(state["values"],np.float32); x0,step,base,maximum,bw=_geometry(w,h,values,template); colors=gradient_colors(template,len(values)); opacity=int(255*np.clip(float(template.get("opacity",1)),0,1)); style=str(template.get("renderer",template.get("style","bars"))).lower(); rgb=np.zeros((h,w,3),np.uint8); alpha=np.zeros((h,w),np.uint8); mirror=bool(template.get("mirror")); points=[]
        def bar(x,a,color,down=False):
            y1,y2=(base,min(h-1,base+a)) if down else (max(0,base-a),base); radius=int(min(bw/2,a/2)*np.clip(float(template.get("roundness",0)),0,1)); cv2.rectangle(rgb,(x-bw//2,y1),(x+bw//2,y2),tuple(map(int,color)),-1,cv2.LINE_AA); cv2.rectangle(alpha,(x-bw//2,y1),(x+bw//2,y2),opacity,-1,cv2.LINE_AA)
            if radius: cy=y2 if down else y1; cv2.circle(rgb,(x,cy),bw//2,tuple(map(int,color)),-1,cv2.LINE_AA); cv2.circle(alpha,(x,cy),bw//2,opacity,-1,cv2.LINE_AA)
        for i,value in enumerate(values):
            a=max(1,int(float(value)*maximum)); x=int(x0+(i+.5)*step); points.append((x,base-a))
            if style=="bars": bar(x,a,colors[i]); mirror and bar(x,a,colors[i],True)
            elif style=="dot":
                radius=max(1,bw//2); cv2.circle(rgb,(x,base-a),radius,tuple(map(int,colors[i])),-1,cv2.LINE_AA); cv2.circle(alpha,(x,base-a),radius,opacity,-1,cv2.LINE_AA)
                if mirror: cv2.circle(rgb,(x,base+a),radius,tuple(map(int,colors[i])),-1,cv2.LINE_AA); cv2.circle(alpha,(x,base+a),radius,opacity,-1,cv2.LINE_AA)
        if style=="line" and len(points)>1:
            segments=list(zip(points[:-1],points[1:])); thickness=max(1,bw)
            for i,(a,b) in enumerate(segments):
                color=tuple(map(int,colors[i])); cv2.line(rgb,a,b,color,thickness,cv2.LINE_AA); cv2.line(alpha,a,b,opacity,thickness,cv2.LINE_AA)
                if mirror: ma=(a[0],2*base-a[1]); mb=(b[0],2*base-b[1]); cv2.line(rgb,ma,mb,color,thickness,cv2.LINE_AA); cv2.line(alpha,ma,mb,opacity,thickness,cv2.LINE_AA)
        if template.get("shadow"):
            shadow=cv2.GaussianBlur(alpha,(0,0),max(1,float(template.get("glow_radius",10))/2)); alpha=np.maximum(alpha,(shadow*.25).astype(np.uint8))
        if template.get("glow"):
            radius=max(.1,float(template.get("glow_radius",10))); strength=max(0,float(template.get("glow_strength",.55))); ga=cv2.GaussianBlur(alpha,(0,0),radius); gr=cv2.GaussianBlur(rgb,(0,0),radius); alpha=np.maximum(alpha,np.clip(ga*strength,0,255).astype(np.uint8)); rgb=np.clip(rgb.astype(np.float32)+gr.astype(np.float32)*strength,0,255).astype(np.uint8)
        return np.dstack((rgb,alpha))
    def _numpy(self,w,h,state,t):
        out=np.zeros((h,w,4),np.uint8); values=np.asarray(state["values"]); x0,step,base,maximum,bw=_geometry(w,h,values,t); colors=gradient_colors(t,len(values)); opacity=int(255*float(t.get("opacity",1)))
        for i,v in enumerate(values):
            a=max(1,int(v*maximum)); x=int(x0+(i+.5)*step); xa,xb=max(0,x-bw//2),min(w,x+bw//2+1); out[max(0,base-a):base+1,xa:xb,:3]=colors[i]; out[max(0,base-a):base+1,xa:xb,3]=opacity
            if t.get("mirror"): out[base:min(h,base+a),xa:xb,:3]=colors[i]; out[base:min(h,base+a),xa:xb,3]=opacity
        return out

class GPUBarRenderer:
    """ModernGL RGBA instancing for bars/dots/line segments; glow uses framebuffer post-processing."""
    name="GPU"
    def __init__(self):
        import moderngl
        self.gl=moderngl; self.ctx=moderngl.create_standalone_context(require=330); self.program=self.ctx.program(vertex_shader='''#version 330
in vec2 corner; in vec4 rect; in vec3 instance_color; uniform vec2 viewport; out vec2 uv; out vec3 vcolor;
void main(){uv=corner;vcolor=instance_color;vec2 p=rect.xy+corner*rect.zw;gl_Position=vec4(p/viewport*2.0-1.0,0,1);}''',fragment_shader='''#version 330
in vec2 uv;in vec3 vcolor;uniform float opacity;uniform int shape;uniform float roundness;out vec4 frag;
void main(){float a=opacity;if(shape==1){float d=length(uv-vec2(.5));a*=smoothstep(.52,.44,d);}else if(roundness>0.0){vec2 q=abs(uv-.5)-vec2(.5-roundness*.45);float d=length(max(q,0.0));a*=1.0-smoothstep(roundness*.44,roundness*.5,d);}frag=vec4(vcolor,a);}'''); self.quad=self.ctx.buffer(np.array([[0,0],[1,0],[0,1],[1,1]],dtype="f4").tobytes())
    def available(self): return True
    def _instances(self,w,h,values,t):
        x0,step,base,maximum,bw=_geometry(w,h,values,t); style=str(t.get("renderer","bars")).lower(); mirror=bool(t.get("mirror")); rects=[]
        for i,v in enumerate(values):
            a=max(1,float(v)*maximum); x=x0+(i+.5)*step-bw/2
            if style=="line": a=max(1,bw); y=h-(base-float(v)*maximum)-a/2
            else: y=h-base
            rects.append((x,y,bw,a))
            if mirror: rects.append((x,h-base-a if style!="line" else h-(base+float(v)*maximum)-a/2,bw,a))
        colors=np.repeat(gradient_colors(t,len(values)),2 if mirror else 1,axis=0).astype("f4")/255
        return np.asarray(rects,"f4"),colors
    def render_rgba(self,w,h,state,t):
        values=np.asarray(state["values"],"f4"); rects,colors=self._instances(w,h,values,t); rb=self.ctx.buffer(rects.tobytes()); cb=self.ctx.buffer(colors.tobytes()); vao=self.ctx.vertex_array(self.program,[(self.quad,"2f","corner"),(rb,"4f/i","rect"),(cb,"3f/i","instance_color")]); tex=self.ctx.texture((w,h),4,dtype="f1"); fbo=self.ctx.framebuffer([tex]); fbo.use(); self.ctx.clear(0,0,0,0); self.ctx.enable(self.gl.BLEND); self.ctx.blend_func=(self.gl.SRC_ALPHA,self.gl.ONE_MINUS_SRC_ALPHA); self.program["viewport"].value=(w,h); self.program["opacity"].value=float(t.get("opacity",1)); self.program["shape"].value=1 if t.get("renderer")=="dot" else 0; self.program["roundness"].value=float(t.get("roundness",0)); vao.render(self.gl.TRIANGLE_STRIP,instances=len(rects)); image=np.frombuffer(fbo.read(components=4,alignment=1),np.uint8).reshape(h,w,4); vao.release(); rb.release(); cb.release(); fbo.release(); tex.release(); image=np.flipud(image).copy()
        if t.get("glow"):
            try:
                import cv2
                blur=cv2.GaussianBlur(image,(0,0),max(.1,float(t.get("glow_radius",10)))); strength=float(t.get("glow_strength",.55)); image=np.clip(image.astype(np.float32)+blur.astype(np.float32)*strength,0,255).astype(np.uint8)
            except ImportError: pass
        return image

class RendererFactory:
    @staticmethod
    def create(choice="AUTO"):
        choice=choice.upper()
        if choice in ("AUTO","GPU"):
            try:return GPUBarRenderer()
            except Exception:
                if choice=="GPU":raise
        return CPURenderer()
