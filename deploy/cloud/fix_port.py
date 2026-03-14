path = '/opt/kwyre/repo/server/serve_local_4bit.py'
with open(path) as f:
    content = f.read()
old = "PORT = int(os.environ.get( KWYRE_PORT, 8000))"
new = "PORT = int(os.environ.get('KWYRE_PORT', '8000'))"
content = content.replace(old, new)
with open(path, 'w') as f:
    f.write(content)
print('Fixed PORT line')
