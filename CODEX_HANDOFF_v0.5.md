# Music Wave Studio v0.5 Codex 지시문
현재 v0.4 단일 스크립트 구조를 폐기하지 말고 기능을 보존하면서 새 4계층 구조로 마이그레이션한다.

1. Audio Analysis Engine: PyAV 우선/FFmpeg fallback 디코딩, FFT/RMS/onset/bass/mid/high, 음원+분석설정 hash 기반 NPZ 캐시.
2. Animation Engine: 시간 t 샘플링, attack/decay, smoothing, onset boost, bass/mid/high weighting, template mapping.
3. Design Renderer: ModernGL instanced quad + GLSL 기반 GPU BAR renderer 완성. 실패 시 CPU 자동 fallback. RGBA를 처음부터 끝까지 유지.
4. Template System: JSON으로 bars/line/dot, gradient, roundness, glow/shadow, mirror, 위치/크기/색/반응값 저장. v0.3/v0.4 preset 호환.
5. v0.4의 다중 레퍼런스 이미지 분석, 직접 ROI, 5~10초 영상 레퍼런스 분석을 모두 유지. 영상 분석값은 attack/decay에 매핑.
6. GUI에 AUTO/GPU/CPU와 PREVIEW/BALANCED/QUALITY 선택 추가.
7. Preview는 0.5배 해상도 24fps. 최종 렌더와 분리.
8. QThread로 분석/렌더하여 UI 정지 금지. 취소, 곡별 진행률, ETA 추가.
9. 15곡 batch에서 한 곡 실패해도 계속하고 error_report.json 생성.
10. 출력: H.264 검정배경 Screen fallback + VP9 alpha WebM + 지원 시 ProRes 4444 MOV.
11. 투명도는 검정 영상에서 threshold로 역산하지 말고 renderer가 true RGBA alpha를 생성.
12. preset gallery + thumbnail preview.
13. pytest: analyzer/cache/animation/template migration/batch failure tests.
14. PyInstaller Windows 빌드 스크립트.
15. 기존 v0.4 기능 회귀 금지.

완료 기준: 동일 음원 재렌더 시 분석 캐시 재사용, 15곡 렌더 중 UI 정상 반응, cancel 가능, GPU 오류 시 CPU fallback, Preview가 final보다 확실히 빠름, true RGBA 출력, 전체 테스트 PASS.
