# video-to-live

Transforma um vídeo curto em Live Photo pra lock screen do iPhone.

CLI v0.2. Sem app. O iOS que decide se anima — aqui a gente reconstitui o `.pvt` que já passou no aparelho (26/08/2026).

## Instala

Precisa de **ffmpeg com libx265** e Python 3.10+.

```bash
sudo apt-get install ffmpeg          # Debian/Ubuntu
# brew install ffmpeg                # macOS

git clone https://github.com/victorsodre/video-to-live
cd video-to-live
```

Confere o HEVC:

```bash
ffmpeg -hide_banner -encoders | grep libx265
```

## Um comando

```bash
python3 -m video_to_live seu-video.mp4
```

Sai `seu-video.pvt/` (e o par HEIC+MOV ao lado). AirDrop **a pasta `.pvt`** e recebe no **Fotos** — não no Files, não zip, não JPG+MOV solto.

O `.HEIC` é JPEG/JFIF 1080×1920 com MakerApple[17] = o UUID do MOV. Foi assim que o par já animou.

## No iPhone

1. AirDrop a pasta `.pvt`
2. Recebe no Fotos
3. Tela de bloqueio → Foto → escolhe a Live Photo

## O que quebra

- **h264 / avc1** — a lock screen ignora
- **vídeo longo** — 3 s nativo não rolou; o container fica em 1,05 s
- **tamanho errado** — 1320×2868 (iPhone 16 Pro Max) também não; fica 1080×1920
- **ffmpeg `-c copy` nas trilhas mebx** — o tag vira `stts` e o iOS ignora. O muxer escreve átomo por átomo.

## A receita (ffmpeg + mux)

Encode HEVC:

```text
-c:v libx265
-tag:v hvc1
-pix_fmt yuv420p
-r 60
-t 1
-frames:v 60
scale/pad 1080x1920
-movie_timescale 600
-video_track_timescale 600
-brand qt
-movflags +faststart
-an
```

O muxer depois deixa o container em 1,05 s (`mvhd` 630/600), `stts` 59×10 + 1×30, hdlr `Core Media Video`, só `content.identifier` + `live-photo.auto=1`, e duas trilhas `mebx`: `live-photo-info` (60 samples) e `still-image-time` (1 sample em 0,5 s). Sem vitality-score.

Não copia mídia de terceiro. O clipe de demo é gerado na hora:

```bash
python3 -m video_to_live --make-demo demo/orbits.mp4
python3 -m video_to_live demo/orbits.mp4 -o /tmp/live
```

## Licença

MIT. Victor ([@ovictor](https://github.com/victorsodre)).
