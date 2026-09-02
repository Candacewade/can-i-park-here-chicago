import requests

#hello! write python code below

#response object for the website we're trying to fetch from:
r = requests.get("https://data.cityofchicago.org/resource/rzy5-8tax.json")

#r will now hold the Response object returned by Chicago’s server, not the website itself. 
#Later, you’ll inspect that response to confirm the request succeeded and extract the JSON data.

