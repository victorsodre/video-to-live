# video-to-live

Transforma um vídeo curto em Live Photo pra lock screen do iPhone.

Abre a página, escolhe o trecho, gera. O iOS que decide se anima — a gente reconstitui o arquivo que já passou no aparelho (26/08/2026).

## Instala

No Mac (ou Linux): **Python 3.10+** e **ffmpeg com libx265**. A página é local; a conversão roda na máquina, não no navegador.

```bash
brew install ffmpeg                # macOS
# sudo apt-get install ffmpeg      # Debian/Ubuntu

git clone https://github.com/victorsodre/video-to-live
cd video-to-live
```

Confere o encoder:

```bash
ffmpeg -hide_banner -encoders | grep libx265
```

## Escolhe o trecho

```bash
python3 -m video_to_live serve
```

Abre `http://127.0.0.1:8765/`. Solta o vídeo, arrasta o início e o fim, aperta **Gerar**. Tela de bloqueio usa ~1s — trecho maior é acelerado pra caber.

A página aceita uploads de até 128 MiB por pedido e processa um vídeo por vez. Só aceita acesso local e formulários da própria origem; o servidor mantém no máximo quatro conexões simultâneas, com 15 segundos de tolerância a inatividade durante o envio. Processos de mídia são encerrados após 120 segundos; consultas com ffprobe, após 30 segundos. Para arquivos maiores que o limite de upload, use a CLI abaixo.

## No iPhone

1. Descompacta se veio zip
2. AirDrop **a pasta `.pvt`**
3. Recebe no **Fotos** — não no Files
4. Tela de bloqueio → Foto → escolhe a Live Photo

## Script

```bash
python3 -m video_to_live clipe.mp4
python3 -m video_to_live clipe.mp4 --start 2.4 --end 8.1 -o saida/
```

`--start` e `--end` são o trecho em segundos. Sem eles, vale o primeiro segundo.

Sai `clipe.pvt/` (e o par HEIC+MOV ao lado). AirDrop a pasta `.pvt` e recebe no Fotos — não zip solto, não JPG+MOV solto.

O still é JPEG/JFIF 1080×1920 nomeado `.HEIC`, com MakerApple[17] = o UUID do MOV.

## O que quebra

- **h264 / avc1** — a lock screen ignora
- **vídeo longo no ritmo original** — 3 s nativo não rolou; o container fica em 1,05 s (trecho maior entra acelerado)
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
