# Python Code Examples

The code example below shows how to make a request for options data using the Python programming language. The example uses the `httpx` HTTP library, which supports both sync and async APIs. This example only uses the sync API, but more information about the async API can be found on the library's site.

**REQUIRED**

The Theta Terminal must be running to access data.

```python
import httpx  # install via pip install httpx
import csv

BASE_URL = "http://localhost:25503/v3"  # all endpoints use this URL base

# set params to fetch a snapshot of all contracts for Microsoft
params = {'symbol': 'MSFT', 'expiration': '*'}

#
# This is the non-streaming version, and the entire response
# will be held in memory.
#
url = BASE_URL + '/option/snapshot/ohlc'

response = httpx.get(url, params=params, timeout=60)  # make the request
response.raise_for_status()  # make sure the request worked

# read the entire response, and parse it as CSV
csv_reader = csv.reader(response.text.split("\n"))

for row in csv_reader:
    print(row)  # do something with the data


#
# This is the streaming version, and will read line-by-line
#
url = BASE_URL + '/option/snapshot/ohlc'

with httpx.stream("GET", url, params=params, timeout=60) as response:
    response.raise_for_status()  # make sure the request worked
    for line in response.iter_lines():
        print(line)  # do something with the data
```

```