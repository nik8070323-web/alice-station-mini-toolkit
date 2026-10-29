#!/usr/bin/env python3
"""Generate original soft UI signals and encode Ogg Opus for YNDX-0004."""
from __future__ import annotations
import math, struct, wave, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WAV=ROOT/'source-wav'; OUT=ROOT/'theme/common'; RATE=48000; PEAK=.12

def tone(name, notes, gaps=0.025):
    samples=[]
    for freqs,dur in notes:
        count=round(RATE*dur)
        fade=min(round(.018*RATE),count//3)
        for i in range(count):
            env=min(1,(i+1)/max(1,fade), (count-i)/max(1,fade))
            if isinstance(freqs,tuple):
                f0,f1=freqs; phase=2*math.pi*(f0*i/RATE+(f1-f0)*i*i/(2*RATE*count))
                value=math.sin(phase)
            elif isinstance(freqs,list):
                value=sum(math.sin(2*math.pi*f*i/RATE) for f in freqs)/len(freqs)
            else:
                value=math.sin(2*math.pi*freqs*i/RATE)
            samples.append(max(-1,min(1,PEAK*env*value)))
        samples.extend([0]*round(RATE*gaps))
    p=WAV/(name+'.wav')
    with wave.open(str(p),'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(b''.join(struct.pack('<h',round(x*32767)) for x in samples))
    return p

files={
 'activation':tone('activation',[((520,620),.11),((740,900),.12)],.008),
 'end-listening':tone('end-listening',[((680,430),.24)],0),
 'volume-click':tone('volume-click',[((980,650),.035)],0),
 'notification':tone('notification',[((520,580),.13),((660,590),.16)],.015),
 'timer':tone('timer',[(523,.24),(659,.24),(784,.30),(659,.24),(523,.40)],.045),
}
map_names={'activation':'spotter_start.mp3','end-listening':'spotter_cancel.mp3','volume-click':'volume_sound.mp3','notification':'notification_sound.mp3','timer':'timer.wav'}
for name,src in files.items():
    dst=OUT/map_names[name]
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(src),'-map_metadata','-1','-c:a','libopus','-application','audio','-b:a','48k','-vbr','constrained','-ar','48000','-ac','1','-f','ogg',str(dst)]
    subprocess.run(cmd,check=True)
    print(name,'->',dst.name)
