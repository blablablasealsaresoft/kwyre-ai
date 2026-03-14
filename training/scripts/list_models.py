from openai import OpenAI
c = OpenAI()
for m in sorted(c.models.list().data, key=lambda x: x.id):
    if any(x in m.id for x in ["gpt", "o1", "o3", "chat", "davinci", "turbo"]):
        print(m.id)
