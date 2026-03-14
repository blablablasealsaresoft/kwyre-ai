import sys
sys.path.insert(0, "/opt/kwyre/repo/security")
from license import validate_license
key = "KWYRE-eyJwIjoiZXlKamRYTjBiMjFsY2lJNkltTnJkR2hsWjJodmMz-UWlMQ0psZUhCcGNtVnpYMkYwSWpwdWRXeHNMQ0pwYzNOMVpX-UmZZWFFpT2pFM056TTBORGMxTVRZc0lteGhZbVZzSWpvaVZX-NXNhVzFwZEdWa0lDaEpiblJsY201aGJDa2lMQ0p0WVdOb2FX-NWxjeUk2T1RrNUxDSjBhV1Z5SWpvaWRXNXNhVzFwZEdWa0lp-d2lkaUk2TVgwPSIsInMiOiJJRm4xWkt3bnhJNGpNeGR5cnhR-SVlpUndvSHZvUDQ2ajRBU1dBRjFjc0R2dEpCL0NLamQ3UVQ3-R29JV1RsTVhuZ2pSc0o4M0txMFU5UnBvQzBldGREdz09In0="
try:
    result = validate_license(key)
    print("VALID:", result)
except Exception as e:
    print("ERROR:", e)
