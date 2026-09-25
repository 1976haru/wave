# Music Wave Studio v0.8.3.1 외부 테스트 가이드

## 시작

1. ZIP 압축을 원하는 폴더에 풉니다. Python, Git, 별도 설치 프로그램은 필요하지 않습니다.
2. `MusicWaveStudio_v0.8.3.1.exe`를 실행합니다.
3. SmartScreen이 표시되면 파일 출처를 확인한 뒤 Windows의 `추가 정보` → `실행` 흐름을 사용합니다.
4. `음원 폴더`에서 샘플 또는 자신의 음원 폴더를 선택합니다.
5. `CHILL RAP SIGNATURE`에서 아래 추천 3개를 차례로 선택합니다.
   - 그와 그녀의 이야기: Symmetric Twin Bloom
   - 그의 이야기: Midnight Mirror Grid
   - 그녀의 이야기: Pearl Stereo Bloom
6. 미리보기 → 대기열에 추가 → 작업 시작을 누릅니다.

## 필수 테스트 항목

1. EXE가 오류 없이 실행되는지 확인합니다.
2. preset gallery에서 추천 메인 3개와 후보 9개가 보이는지 확인합니다.
3. `validation_results/v0831_signature_redesign/videos`의 10초 샘플을 확인합니다.
4. `sample_assets/sample_music_set` 또는 자신의 15곡 폴더로 SET 모드 출력 1개가 만들어지는지 확인합니다.
5. MP4를 CapCut 위 트랙에 놓고 혼합(Blend) `Screen(스크린)` 상태를 확인합니다.
6. Dual/His/Her 각 3안 중 가장 예쁜 안을 하나씩 고릅니다.
7. 색, 움직임, 존재감, 복잡도에서 부족한 점을 `FEEDBACK_FORM_KR.txt`에 적습니다.

## 위치

- EXE: `dist/MusicWaveStudio_v0.8.3.1/MusicWaveStudio_v0.8.3.1.exe`
- 샘플 음원: `sample_assets/sample_music_set`
- 9안 비교 결과: `validation_results/v0831_signature_redesign`
- 피드백 양식: `FEEDBACK_FORM_KR.txt`

## 오류 전달

`%LOCALAPPDATA%/MusicWaveStudio/logs/music_wave_studio.log`와 오류 메시지를 전달해 주세요. 개인 음원은 전달하지 않아도 됩니다.
