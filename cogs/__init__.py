def __init__(self, bot):
        self.bot = bot
        # Configurações otimizadas para evitar erros de JavaScript
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            'outtmpl': 'temp/musica_%(id)s.%(ext)s',
            'quiet': True,
            'nocheckcertificate': True, # Ignora erros de certificado SSL
            'ignoreerrors': False,
            'logtostderr': False,
            'no_warnings': True,
            # O TRUQUE: Fingir que somos um Android para pular o JS chato
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'skip': ['hls', 'dash']
                }
            }
        }