# Architecture
Audio → FFmpeg/PyAV decode → FFT/RMS/onset/bass-mid-high analysis → `.npz` cache → current time t → AnimationEngine (attack/decay/template mapping) → ModernGL GPU renderer or CPU fallback → true RGBA → preview / FFmpeg export.

Preview는 저해상도/24fps, 최종 렌더는 별도 품질 프로필을 사용합니다. 분석 캐시는 재사용하므로 같은 음원을 렌더할 때 FFT를 반복 계산하지 않습니다.
