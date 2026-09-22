from __future__ import annotations
import numpy as np


def _color(value):
    value=value.lstrip("#"); return tuple(int(value[i:i+2],16) for i in (0,2,4))

class CPURenderer:
    name="CPU"
    def render_rgba(self,w,h,state,template):
        try:
            import cv2
        except ImportError:
            return self._render_numpy(w,h,state,template)
        rgb=np.zeros((h,w,3),np.uint8); alpha=np.zeros((h,w),np.uint8)
        values=np.asarray(state["values"]); usable=max(1,int(w*float(template.get("width",.72)))); x0=(w-usable)//2
        positions={"top":int(h*.2),"center":int(h*.5),"bottom":int(h*.82)}; base=positions.get(template.get("position","bottom"),int(h*.82))
        step=usable/max(1,len(values)); maximum=int(h*float(template.get("height",.22))); color=_color(template.get("color","#FFFFFF")); opacity=int(255*float(template.get("opacity",1)))
        style=template.get("renderer",template.get("style","bars")); points=[]
        for i,value in enumerate(values):
            amplitude=max(1,int(float(value)*maximum)); x=int(x0+(i+.5)*step); points.append((x,base-amplitude))
            if style=="bars":
                bw=max(1,int(step*float(template.get("bar_width",.55)))); radius=int(min(bw/2,amplitude/2)*float(template.get("roundness",0)))
                cv2.rectangle(rgb,(x-bw//2,base-amplitude),(x+bw//2,base),color,-1,cv2.LINE_AA); cv2.rectangle(alpha,(x-bw//2,base-amplitude),(x+bw//2,base),opacity,-1,cv2.LINE_AA)
                if radius: cv2.circle(rgb,(x,base-amplitude),bw//2,color,-1,cv2.LINE_AA); cv2.circle(alpha,(x,base-amplitude),bw//2,opacity,-1,cv2.LINE_AA)
                if template.get("mirror"): cv2.rectangle(rgb,(x-bw//2,base),(x+bw//2,min(h-1,base+amplitude)),color,-1,cv2.LINE_AA); cv2.rectangle(alpha,(x-bw//2,base),(x+bw//2,min(h-1,base+amplitude)),opacity,-1,cv2.LINE_AA)
            elif style=="dot": cv2.circle(rgb,(x,base-amplitude),max(1,int(step*float(template.get("bar_width",.55))/2)),color,-1,cv2.LINE_AA); cv2.circle(alpha,(x,base-amplitude),max(1,int(step*.25)),opacity,-1,cv2.LINE_AA)
        if style=="line" and len(points)>1:
            pts=np.asarray(points,np.int32); thickness=max(1,int(step*float(template.get("bar_width",.3)))); cv2.polylines(rgb,[pts],False,color,thickness,cv2.LINE_AA); cv2.polylines(alpha,[pts],False,opacity,thickness,cv2.LINE_AA)
        if template.get("glow"):
            radius=max(1,float(template.get("glow_radius",10))); glow_a=cv2.GaussianBlur(alpha,(0,0),radius); glow_rgb=cv2.GaussianBlur(rgb,(0,0),radius); alpha=np.maximum(alpha,(glow_a*.55).astype(np.uint8)); rgb=cv2.addWeighted(rgb,1,glow_rgb,.55,0)
        return np.dstack((rgb,alpha))
    def _render_numpy(self,w,h,state,template):
        out=np.zeros((h,w,4),np.uint8); values=np.asarray(state["values"]); usable=max(1,int(w*float(template.get("width",.72)))); x0=(w-usable)//2; step=usable/max(1,len(values)); base={"top":int(h*.2),"center":int(h*.5),"bottom":int(h*.82)}.get(template.get("position","bottom"),int(h*.82)); maximum=int(h*float(template.get("height",.22))); color=_color(template.get("color","#FFFFFF")); opacity=int(255*float(template.get("opacity",1)))
        for i,value in enumerate(values):
            amplitude=max(1,int(float(value)*maximum)); x=int(x0+(i+.5)*step); bw=max(1,int(step*float(template.get("bar_width",.55)))); xa=max(0,x-bw//2); xb=min(w,x+bw//2+1); ya=max(0,base-amplitude); yb=min(h,base+1); out[ya:yb,xa:xb,:3]=color; out[ya:yb,xa:xb,3]=opacity
            if template.get("mirror"): out[base:min(h,base+amplitude),xa:xb,:3]=color; out[base:min(h,base+amplitude),xa:xb,3]=opacity
        return out

class GPUBarRenderer:
    """ModernGL instanced bars rendered directly into an RGBA framebuffer."""
    name="GPU"
    def __init__(self):
        import moderngl
        self.moderngl=moderngl; self.ctx=moderngl.create_standalone_context(require=330)
        self.program=self.ctx.program(vertex_shader='''#version 330
        in vec2 corner; in vec4 rect; uniform vec2 viewport;
        void main(){ vec2 p=rect.xy+corner*rect.zw; gl_Position=vec4(p/viewport*2.0-1.0,0.0,1.0); }''', fragment_shader='''#version 330
        uniform vec4 color; out vec4 frag; void main(){ frag=color; }''')
        self.quad=self.ctx.buffer(np.array([[0,0],[1,0],[0,1],[1,1]],dtype="f4").tobytes())
    def available(self): return self.ctx is not None
    def render_rgba(self,w,h,state,template):
        values=np.asarray(state["values"],dtype="f4"); usable=w*float(template.get("width",.72)); x0=(w-usable)/2; step=usable/max(1,len(values)); base={"top":h*.2,"center":h*.5,"bottom":h*.82}.get(template.get("position","bottom"),h*.82); maximum=h*float(template.get("height",.22)); bw=max(1,step*float(template.get("bar_width",.55)))
        rects=np.array([[x0+(i+.5)*step-bw/2,h-base,bw,max(1,float(v)*maximum)] for i,v in enumerate(values)],dtype="f4")
        instances=self.ctx.buffer(rects.tobytes()); vao=self.ctx.vertex_array(self.program,[(self.quad,"2f","corner"),(instances,"4f/i","rect")]); texture=self.ctx.texture((w,h),4,dtype="f1"); fbo=self.ctx.framebuffer([texture]); fbo.use(); self.ctx.clear(0,0,0,0); self.ctx.enable(self.moderngl.BLEND); self.ctx.blend_func=(self.moderngl.SRC_ALPHA,self.moderngl.ONE_MINUS_SRC_ALPHA)
        color=_color(template.get("color","#FFFFFF")); self.program["viewport"].value=(w,h); self.program["color"].value=(*(c/255 for c in color),float(template.get("opacity",1))); vao.render(self.moderngl.TRIANGLE_STRIP,instances=len(values)); data=np.frombuffer(fbo.read(components=4,alignment=1),np.uint8).reshape(h,w,4); vao.release(); instances.release(); fbo.release(); texture.release(); return np.flipud(data).copy()

class RendererFactory:
    @staticmethod
    def create(choice="AUTO"):
        choice=choice.upper()
        if choice in ("AUTO","GPU"):
            try: return GPUBarRenderer()
            except Exception:
                if choice=="GPU": raise
        return CPURenderer()
