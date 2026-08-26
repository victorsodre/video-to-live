# video-to-live

Transforma um vídeo curto em Live Photo pra lock screen do iPhone.

CLI v0.1. Sem app. O iOS que decide se anima — aqui a gente reconstitui a receita que já funcionou no aparelho (26/08/2026): HEVC `hvc1`, 1080×1920, ~1 s, 60 fps.

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

Sai no mesmo lugar (ou em `-o pasta/`):

- `seu-video.MOV`
- `seu-video.HEIC`
- `seu-video.pvt/` — HEIC + MOV + `metadata.plist` (`PFVideoComplementMetadataVersionKey=1`)

O `.HEIC` é JPEG/JFIF 1080×1920 com MakerApple[17] = o UUID do MOV. Foi assim que o par já animou na lock screen; um HEIC “de verdade” também serve se o UUID bater.

## No iPhone

1. AirDrop o par (os dois arquivos, ou a pasta `.pvt`)
2. Abre no Fotos
3. Tela de bloqueio → Foto → escolhe a Live Photo

## O que quebra

- **h264 / avc1** — a lock screen ignora
- **vídeo longo** — 3 s nativo não rolou; o padrão é ~1 s
- **tamanho errado** — 1320×2868 (iPhone 16 Pro Max) também não; fica 1080×1920

## A receita (ffmpeg)

O que importa no encode:

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

Depois o CLI injeta:

- `com.apple.quicktime.content.identifier` (UUID)
- `com.apple.quicktime.live-photo.auto=1`
- duas trilhas `mebx` Core Media: `video-orientation` no clipe inteiro, `still-image-time` de ~1 quadro no meio

Não copia mídia de terceiro. O clipe de demo é gerado na hora:

```bash
python3 -m video_to_live --make-demo demo/orbits.mp4
python3 -m video_to_live demo/orbits.mp4 -o /tmp/live
```

## Licença

MIT. Victor ([@ovictor](https://github.com/victorsodre)).
