from decouple import config
import moncash
gateway = moncash.Moncash(
    client_id=config('MONCASH_CLIENT_ID'),
    client_secret=config('MONCASH_SECRET_KEY'),
    environment=moncash.environment.Sandbox
)