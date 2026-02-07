import requests
from github import Github
from github import Auth
from dotenv import load_dotenv
import os
# load env
load_dotenv()
token = os.getenv("TOKEN")
auth = Auth.Token(token)
g = Github(auth=auth)

repositories = g.search_repositories(query='language:dart app')

for repository in repositories:
    zip_url = repository.get_archive_link("zipball")
    response = requests.get(zip_url)
    with open(f"../assets/{repository.full_name.replace('/', '-')}.zip", "wb") as f:
        f.write(response.content)
    break

