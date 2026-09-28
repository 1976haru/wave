# Music Wave Studio v0.8.5.0-dev

## Tokyo Chill Signature V1 (사용자 시각 검토 필요)

- 그의 STORY: Tokyo Midnight Pulse
- 그녀의 STORY: Tokyo Silk Wave
- 그와 그녀의 STORY: Tokyo Two Hearts
- 4단계 움직임, 70–130% 크기, 상/중/하 위치, 3단계 존재감
- Universal Visualizer와 기존 Tokyo preset은 그대로 유지합니다.

## Local Background Adapt

- 전체 화면 평균이 아닌 실제 파형 lower-third ROI의 밝기, 대비, highlight, texture를 분석합니다.
- 밝고 복잡한 배경에서는 theme 색에서 파생한 미세한 contrast halo와 강화된 core로 가독성을 높입니다.
- 어두운 배경의 기존 glow 품질과 Soft Round LED geometry/motion은 유지합니다.
- Preview와 production Render가 선택한 reference 이미지/영상에 동일한 adaptation 경로를 사용합니다.

## Universal Visualizer Production Integration

- Soft Round LED renderer family와 범용 Theme 7종
- 독립적인 Intensity / Width / Position / Custom Color / Auto Adapt
- AppData에 유지되는 My Waveforms
- JSON-only `.mwswave` Import / Export 및 schema validation
- 기존 template과 queue/resume 호환 유지

## Chill Girl Vibes Lower-Third Dotted Wave

- Premium Neon Dots 방향에서 감성적인 lower-third dotted wave로 전환했습니다.
- 더 풍부하지만 부드러운 dotted body와 rounded mound/skyline 형태를 적용했습니다.
- isolated hero pole과 harsh white marker를 제거했습니다.
- top contour 없이 floor-anchor/upward-only 구조를 유지합니다.
- 실제 Tokyo Chill 배경 composition review를 다시 생성합니다.

## Premium Neon Dots

- 그래프처럼 보이던 top contour를 완전히 제거했습니다.
- strongest hero peak와 neon accent dot 중심으로 시각 계층을 재구성했습니다.
- pillar 내부 fill density와 baseline 강조를 더 낮췄습니다.
- floor-anchor 및 upward-only 구조는 그대로 유지합니다.
- 실제 Tokyo Chill 배경 composition review를 다시 생성합니다.

## Sparse Neon Signature

- Tokyo Chill 시그니처의 band와 column 밀도를 낮춰 여백을 강화했습니다.
- 소수의 hero peak와 절제된 neon highlight 중심으로 시각 계층을 정리했습니다.
- premium하고 젊은 Chill / Night Drive 분위기로 튜닝했습니다.
- 하단 고정, upward-only geometry, adaptive normalization 구조는 그대로 유지합니다.

## 이번 업그레이드 핵심

- Tokyo Chill 시그니처 3종의 기준선을 화면 높이 약 82% 지점에 고정했습니다.
- 파형이 기준선 아래로 내려가지 않고 음악 에너지에 따라 위쪽으로만 크게 상승합니다.
- 잔잔한 구간과 강한 구간의 높이 차이를 확대해 장시간 플레이리스트에서도 움직임이 평평해 보이지 않도록 조정했습니다.
- 색상 변화가 단순 시간 흐름뿐 아니라 파형 높이, 에너지, onset 강도에 함께 반응합니다.
- 강한 피크에서는 상단 highlight/spark가 추가되어 비트의 순간 상승을 더 분명하게 표시합니다.
- 남성/듀얼 시그니처는 DYNAMIC, 여성 시그니처는 DYNAMIC_SOFT로 성격을 분리했습니다.
- 좌/우 지연 신호는 전체 주파수 범위를 유지하도록 보정했고 상단 envelope의 구간 연결도 이어지도록 수정했습니다.

## 회귀 방지

`tests/test_v0836_floor_anchor.py`에서 다음을 고정 검증합니다.

- 하단 기준선 고정
- 기준선 아래 geometry 생성 금지
- 강한 음악에서 최소 45px 이상의 추가 상승폭
- 강한 상태에서 총 상승 높이 85px 이상
- 에너지와 시간에 따른 색상 변화
- v0.8.3.7 sparse-neon floor-anchor 템플릿 파라미터

## 기본 출력

- 960x160
- 24fps
- H.264 / CRF18
- 검정 배경
- CapCut Screen 합성 workflow

실제 GitHub Release publish는 사용자 승인 후 진행합니다.
