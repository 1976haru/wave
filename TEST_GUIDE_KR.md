# Music Wave Studio v0.8.3.4 Beta 테스트 가이드

## 프로그램 테스트

1. ZIP을 별도 폴더에 완전히 압축 해제합니다.
2. `MusicWaveStudio_v0.8.3.4.exe`를 실행합니다.
3. `sample_assets` 또는 본인의 15곡 폴더를 선택합니다.
4. 추천 영역에서 Tokyo Twin Flow, Tokyo Midnight Flow, Tokyo Pearl Flow를 각각 확인합니다.
5. 미리보기 후 대기열에 추가하고 작업을 시작합니다.
6. 15곡이 개별 영상 15개가 아닌 SET 영상 1개로 생성되는지 확인합니다.
7. 2개 SET을 넣었을 때 결과 MP4가 2개만 생성되는지 확인합니다.

## CapCut Screen 체크리스트

1. 완성된 MP4를 CapCut에 import합니다.
2. 본 영상보다 위쪽 track에 배치합니다.
3. 혼합/Blend 메뉴를 엽니다.
4. Screen을 선택합니다.
5. 검정 배경이 깨끗하게 사라지는지 확인합니다.
6. 파형 색과 선명도를 확인합니다.
7. 일본어/영어 subtitle과 충돌하지 않는지 확인합니다.

## 종료 테스트

렌더 완료 후 프로그램을 닫고 작업 관리자에서 MusicWaveStudio, ffmpeg 또는 관련 프로세스가 남지 않는지 확인합니다.

문제가 생기면 `logs/music_wave_studio.log` 또는 `%LOCALAPPDATA%\MusicWaveStudio\logs\music_wave_studio.log`와 피드백 양식을 함께 전달해 주세요. 음원 파일 자체는 전달하지 않아도 됩니다.
