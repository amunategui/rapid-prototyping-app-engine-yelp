from flask import Flask, render_template, flash, request, jsonify
from wtforms import Form, TextField, TextAreaField, validators, StringField, SubmitField
import requests
import json
import logging
import requests_toolbelt.adapters.appengine

requests_toolbelt.adapters.appengine.monkeypatch()

try:
    # For Python 3.0 and later
    from urllib.error import HTTPError
    from urllib.parse import quote
    from urllib.parse import urlencode
except ImportError:
    # Fall back to Python 2's urllib2 and urllib
    from urllib2 import HTTPError
    from urllib import quote
    from urllib import urlencode

# App config.
DEBUG = True
app = Flask(__name__)

GOOGLE_API_KEY = "ADD YOUR GOOGLE MAPS API KEY HERE"
# https://github.com/Yelp/yelp-fusion/blob/master/fusion/python/sample.py
YELP_API_KEY = 'ADD YOUR YELP DEVELOPER API KEY HERE'
# API constants, you shouldn't have to change these.
API_HOST = 'https://api.yelp.com'
SEARCH_PATH = '/v3/businesses/search'

def linspace(start, stop, n):
    # https://stackoverflow.com/questions/12334442/does-python-have-a-linspace-function-in-its-std-lib
    if n == 1:
        yield stop
        return
    h = (stop - start) / (n - 1)
    for i in range(n):
        yield start + h * i

def get_distance_between_geocoordinates(lat1, lon1, lat2, lon2):
    from math import sin, cos, sqrt, atan2, radians
    # https://stackoverflow.com/questions/19412462/getting-distance-between-two-points-based-on-latitude-longitude/19412565
    # approximate radius of earth in km
    R = 6373.0

    # convert from degrees to radians
    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    # conversion factor
    conv_fac = 0.621371

    # calculate miles
    miles = (R * c) * conv_fac

    return(miles)

def GetBestYelpLocation(host, path, api_key, term, latitude, longitude):
    """Given your api_key, send a GET request to the API.
    Args:
        host: domain host of the API.
        path: path of the API after the domain.
        api_key: API Key
        term: search term
        latitude: latitude
        longitude: longitude
    Returns:
        DataFrame: top business found
    """
    # build url paramaters to append to GET string
    url_params = {
    'term': term.replace(' ', '+'),
    'latitude':latitude,
    'longitude':longitude,
    'limit': 1
    }

    # finalize
    url_params = url_params or {}
    url = '{0}{1}'.format(host, quote(path.encode('utf8')))
    headers = {
        'Authorization': 'Bearer %s' % api_key,
    }

    response = requests.request('GET', url, headers=headers, params=url_params)
    response = response.json()
    rez = None
    if response['total'] > 0:
        rez = ({"name":[response['businesses'][0]['name']],
           'city':[response['businesses'][0]['location']['city']],
           'rating':[response['businesses'][0]['rating']],
           'latitude':[response['region']['center']['latitude']],
           'longitude':[response['region']['center']['longitude']],
           'state':[response['businesses'][0]['location']['state']]})
    return (rez)

def GetGeoSteps(starting_coords, ending_coords, step_count):
    """Given starting_coords,ending_coords and step_count
    Args:
        starting_coords: latitude and longitude of starging point
        ending_coords: latitude and longitude of ending point
        step_count: how many steps to create
    Returns:
        list: of coordinates
    """
    # how many steps to go from one point to another?
    lats = linspace(starting_coords[0], ending_coords[0], step_count)
    longs = linspace(starting_coords[1], ending_coords[1], step_count)
    coords = [(lat, lon) for lat, lon in zip(lats, longs)]
    return (coords)

class ReusableForm(Form):
    deparature = TextField('deparature', validators=[validators.required()])
    destination = TextField('destination', validators=[validators.required()])
    search_term = TextField('search_term', validators=[validators.required()])

@app.errorhandler(500)
def server_error(e):
    logging.exception('some eror')
    return """
    And internal error <pre>{}</pre>
    """.format(e), 500

@app.route('/background_process', methods=['GET', 'POST'])
def background_process():
    current_lat = float(request.args.get('current_lat'))
    current_lon = float(request.args.get('current_lon'))
    end_lat = float(request.args.get('end_lat'))
    end_lon = float(request.args.get('end_lon'))
    steps_remaining = int( request.args.get('steps_remaining'))
    search_term = request.args.get('search_term')

    next_coords = GetGeoSteps(starting_coords=[current_lat,current_lon], ending_coords=[end_lat,end_lon], step_count = steps_remaining)
    trip_data = GetBestYelpLocation(API_HOST, SEARCH_PATH, YELP_API_KEY, search_term, next_coords[1][0], next_coords[1][1])

    if (trip_data is not None):
        return jsonify({'result': steps_remaining, 'next_coords': [str(trip_data['city'][0]), float(trip_data['latitude'][0]),
        float(trip_data['longitude'][0]), str(trip_data['name'][0]), str(trip_data['rating'][0])]})
    else:
        return jsonify({'result': steps_remaining, 'next_coords': ["Nothing found here", float(next_coords[1][0]), float(next_coords[1][1]), "No business found", 0]})


@app.route("/", methods=['GET', 'POST'])
def index():
    return render_template('index.html')

@app.route("/map", methods=['POST', 'GET'])
def get_information():
    form = ReusableForm(request.form)
    print (form.errors)

    if request.method == 'POST':
        departure=request.form['departure']
        departure = departure.replace(' ', '+')

        destination=request.form['destination']
        destination = destination.replace(' ', '+')

        search_term=request.form['search_term']
        search_term = search_term.replace(' ', '+')

        response = requests.get('https://maps.googleapis.com/maps/api/geocode/json?address=' + departure + '&key=' + GOOGLE_API_KEY)
        resp_json_payload = response.json()
        departure_coords = resp_json_payload['results'][0]['geometry']['location']
        departure = str(resp_json_payload['results'][0]['formatted_address'])

        response = requests.get('https://maps.googleapis.com/maps/api/geocode/json?address=' + destination + '&key=' + GOOGLE_API_KEY)
        resp_json_payload = response.json()
        destination_coords = resp_json_payload['results'][0]['geometry']['location']
        destination = str(resp_json_payload['results'][0]['formatted_address'])

        # attempt to do this trip in 50-mile chuncks
        steps_remaining = int(get_distance_between_geocoordinates(float(departure_coords['lat']), float(departure_coords['lng']), float(destination_coords['lat']), float(destination_coords['lng']))/50.0)
        steps_remaining = steps_remaining - 1
        if (steps_remaining < 1): steps_remaining = 1

        # pass first and last position info
        init_points = [[departure, departure_coords['lat'], departure_coords['lng'], 'Starting location', 5], [destination, destination_coords['lat'], destination_coords['lng'], 'Ending location', 5]]

        return render_template('map.html', init_points = init_points, search_term=search_term, steps_remaining=steps_remaining, departure=departure, destination=destination)
    else:
        return render_template('index.html', form=form)

if __name__ == '__main__':
    app.run()

