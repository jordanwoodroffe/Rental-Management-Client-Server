import json
import random
from datetime import datetime
import pandas as pd
from json.decoder import JSONDecodeError
import requests
from sqlalchemy import MetaData, Table, Column, DateTime, Integer, Float, String, insert, select, update, delete, \
    ForeignKey, LargeBinary
from flask import Blueprint, request, Response, Flask
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from marshmallow import fields
from sqlalchemy.orm import sessionmaker
from utils import get_random_alphaNumeric_string, hash_password, verify_password, compare_dates
from sqlalchemy.dialects.mysql import TINYINT, VARCHAR, TEXT
from environs import Env

"""
Instructions:
https://cloud.google.com/sql/docs/mysql/connect-external-app

Enable Cloud SQL Admin API for the project.

Create a new Google Cloud SQL Instance, then create a database.

    Copy the INSTANCE_CONNECTION_NAME from overview screen

Install the proxy client (as per google doc instructions), make it executable 

Invoke proxy:
    ./cloud_sql_proxy -instances=<INSTANCE_CONNECTION_NAME>=tcp:<PORT> &
    
And update the below/db code to use the right port number, database name, etc.
"""
env = Env()
env.read_env()

DB_NAME = env("DB_NAME")
DB_USER = env("DB_USER")
DB_PASS = env("DB_PASS")
PORT_NUMBER = env("PORT_NUMBER")
DB_URI = "mysql+pymysql://{}:{}@127.0.0.1:{}/{}".format(DB_USER, DB_PASS, PORT_NUMBER, DB_NAME)

api = Blueprint("api", __name__)

db = SQLAlchemy()
engine = db.create_engine(
    sa_url=DB_URI,
    engine_opts={"echo": True}
)
session = sessionmaker(engine)

ma = Marshmallow()


class User(db.Model):
    __tablename__ = "user"
    email = db.Column('email', VARCHAR(45), primary_key=True, nullable=False)
    f_name = db.Column('first_name', VARCHAR(45), nullable=False)
    l_name = db.Column('last_name', VARCHAR(45), nullable=False)
    password = db.Column('password', TEXT(75), nullable=False)


class Car(db.Model):
    __tablename__ = "car"
    car_id = db.Column('car_id', VARCHAR(6), primary_key=True, nullable=False)
    model_id = db.Column('model_id', Integer(), ForeignKey('car_model.model_id'), nullable=False)
    model = db.relationship("CarModel")
    name = db.Column('name', VARCHAR(45), nullable=False)
    cph = db.Column('cph', Float())
    locked = db.Column('available', TINYINT(1), nullable=False)
    long = db.Column('long', Float())
    lat = db.Column('lat', Float())


class CarModel(db.Model):
    __tablename__ = "car_model"
    model_id = db.Column('model_id', Integer(), primary_key=True, nullable=False, autoincrement=True)
    make = db.Column('make', VARCHAR(45), nullable=False)
    model = db.Column('model', VARCHAR(45), nullable=False)
    year = db.Column('year', Integer(), nullable=False)
    capacity = db.Column('capacity', Integer(), nullable=False)
    colour = db.Column('colour', VARCHAR(45), nullable=False)


class Booking(db.Model):
    __tablename__ = "booking"
    booking_id = db.Column('booking_id', Integer(), primary_key=True, nullable=False, autoincrement=True)
    user_id = db.Column('user_email', VARCHAR(45), ForeignKey('user.email'), nullable=False)
    user = db.relationship('User')
    car_id = db.Column('car_id', VARCHAR(6), ForeignKey('car.car_id'), nullable=False)
    car = db.relationship('Car')
    start = db.Column('start', DateTime(), nullable=False)
    end = db.Column('end', DateTime(), nullable=False)
    completed = db.Column('completed', Integer(), nullable=False)
    event_id = db.Column('event_id', VARCHAR(45))


class Encoding(db.Model):
    __tablename__ = "encoding"
    enc_id = db.Column('image_id', Integer(), primary_key=True, nullable=False, autoincrement=True)
    user_id = db.Column('user_email', VARCHAR(45), ForeignKey('user.email'), nullable=False)
    user = db.relationship('User')
    data = db.Column('data', LargeBinary(length=(2 ** 32) - 1), nullable=False)
    name = db.Column('name', VARCHAR(45), nullable=False)
    type = db.Column('type', VARCHAR(45), nullable=False)
    size = db.Column('size', VARCHAR(45), nullable=False)
    details = db.Column('details', VARCHAR(45), nullable=False)


class UserSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = User

    email = ma.auto_field()
    f_name = ma.auto_field()
    l_name = ma.auto_field()


class CarModelSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = CarModel

    model_id = ma.auto_field()
    make = ma.auto_field()
    model = ma.auto_field()
    year = ma.auto_field()
    capacity = ma.auto_field()
    colour = ma.auto_field()


class CarSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Car

    car_id = ma.auto_field()
    name = ma.auto_field()
    model_id = ma.auto_field()
    model = fields.Nested(CarModelSchema)
    locked = ma.auto_field()
    cph = ma.auto_field()
    long = ma.auto_field()
    lat = ma.auto_field()


class BookingSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Booking

    booking_id = ma.auto_field()
    user_id = ma.auto_field()
    user = fields.Nested(UserSchema)
    car_id = ma.auto_field()
    car = fields.Nested(CarSchema)
    start = ma.auto_field()
    end = ma.auto_field()
    completed = ma.auto_field()
    event_id = ma.auto_field()


class EncodingSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Encoding

    enc_id = ma.auto_field()
    user_id = ma.auto_field()
    user = fields.Nested(UserSchema)
    data = ma.auto_field()
    name = ma.auto_field()
    type = ma.auto_field()
    size = ma.auto_field()
    details = ma.auto_field()


def create_app():
    app = Flask(__name__)
    db.init_app(app)
    return app

"""
Database RESTful API
provides endpoints for accessing, inserting, and updating data from Google Cloud SQL Database
"""


@api.route("/users", methods=['GET'])
def get_users():
    """
    Endpoint to return ALL users from database (used in testing)
    """
    users = User.query.all()
    if users is not None:
        return Response(
            UserSchema(many=True, exclude=['password']).dumps(users), status=200, mimetype="application/json"
        )
    return Response("No users found", status=500)


@api.route("/user", methods=['GET'])
def get_user():
    """
    Returns a specific user from the database

    Params:
        user_id: id of user to fetch from db

    Returns:
        user data in json format
    """
    user_id = request.args.get('user_id')
    if user_id is not None:
        user = User.query.get(user_id)
        if user is not None:
            return Response(UserSchema(exclude=['password']).dumps(user), status=200, mimetype="application/json")
        return Response("User {} not found".format(user_id), status=404)
    return Response("user_id param not found", status=400)


@api.route("/user", methods=['POST'])
def add_user():
    """
    Adds a user to the database

    Params:
        user_data: data to be added (name, email, password)

    Returns:
        200 if successful, 404 if email already registered, 400 if client errors, or 500 if exceptions raised
    """
    user_data = request.get_json()
    response = None
    try:
        if user_data is None:
            response = Response(status=400)
        else:
            data = json.loads(user_data)
            user = User.query.get(data['email'])
            if user is None:
                salt = get_random_alphaNumeric_string(10)
                user = User()
                user.email = data['email']
                user.f_name = data['f_name']
                user.l_name = data['l_name']
                user.password = hash_password(data['password'], salt) + ':' + salt
                db.session.add(user)
                db.session.commit()
                response = Response(status=200)
            else:
                response = Response(status=404)
    except JSONDecodeError as de:
        print("{}\n{}".format("Unable to decode user object", str(de)))
        response = Response(status=500)
    except ValueError as ve:
        print("{}\n{}".format("Unable to access value", str(ve)))
        response = Response(status=500)
    finally:
        return response


@api.route("/users/authenticate", methods=['GET', 'POST'])
def user_authentication():
    """
    Endpoint to authenticate a user logging in to MP webapp

    Params:
        user_id: email input from user attempting login
        password: password input from user attempting login

    Returns:
        JSON object containing a success/error code and user data if successful
    """
    user_id = request.args.get('user_id')
    password = request.args.get('password')
    # response = {}
    if user_id is None:
        response = Response("No email parameter found", status=400)
        # response['code'] = 'EMAIL ERROR'
    elif password is None:
        response = Response("No password parameter found", status=400)
        # response['code'] = 'PASSWORD ERROR'
    else:
        user = User.query.get(user_id)
        if user is not None:
            stored_password = user.password.split(':')[0]
            salt = user.password.split(':')[1]
            if verify_password(stored_password, password, salt):
                response = Response(
                    UserSchema(exclude=['password']).dumps(user), status=200, content_type="application/json"
                )
                # response['code'] = 'SUCCESS'
                # response['user'] = UserSchema(exclude=['password']).dumps(user)
            else:
                response = Response(json.dumps({'error': 'PASSWORD'}), status=404, content_type="application/json")
                # response['code'] = 'PASSWORD ERROR'
        else:
            response = Response(json.dumps({'error': 'EMAIL'}), status=404, content_type="application/json")
            # response['code'] = 'EMAIL ERROR'
    return response


@api.route("/cars", methods=['GET'])
def get_cars():
    """
    Endpoint to return a list of car objects, checks for param available=1 (returns only non-booked cars)
    """
    cars = Car.query.all()
    if cars is not None:
        return Response(CarSchema(many=True).dumps(cars), status=200, mimetype="application/json")
    return Response("No cars found", status=500)


@api.route("/car", methods=['GET'])
def get_car():
    """
    Endpoint to return a car from the database

    Params:
        car_id: id of car to fetch

    Returns:
        JSON object representing car
    """
    car_id = request.args.get('car_id')
    data = None
    if car_id is not None:
        car = Car.query.get(car_id)
        if car is not None:
            return Response(CarSchema().dumps(car), status=200, mimetype="application/json")
        return Response("Car not found", status=404)
    return Response("car_id param was not found", status=400)


@api.route("/car", methods=['PUT'])
def update_car():
    """
    Endpoint to update a car - called from MP after it receives login information from AP. First, bookings matching
    the user_id and car_id are retrieved, and if they are valid (i.e. have not been completed or are within their
    start/end dates) then the car is unlocked.
    If the car is to be locked, then the booking is also marked as completed.
    If no user_id or locked value are included, this function calls update_location(car_id)

    Params:
        car_id: id of car to unlock
        locked: locked value to update to (1= locked, 0= unlocked)
        user_id: id of user in db

    Returns:
        200 if successful, 404 if no valid results found, or 400 if there are client errors
    """
    car_id = request.args.get('car_id')
    if car_id is not None:
        locked = request.args.get('locked')
        user_id = request.args.get('user_id')
        if None in (user_id, locked):
            return update_location(car_id)
        else:
            try:
                locked_val = int(locked)
            except ValueError as e:
                return Response("Invalid locked format: expected 1 or 0.\n".format(str(e)), status=400)
            status = 1 if locked_val == 0 else 0  # current locked status should be opposite of new status
            # query returns uncompleted bookings for the user and car, where the car.locked = status
            bookings = Booking.query\
                .filter_by(completed=0).filter_by(car_id=car_id).filter_by(user_id=user_id)\
                .join(Car).filter(Car.car_id == car_id).filter_by(locked=status)
            if bookings.count() > 0:  # if any bookings were found
                valid_bookings = []
                for booking in bookings:
                    # TODO: booking.start <= datetime.now() <= booking.end? check overdue return?
                    if booking.start <= datetime.now():  # booking has started and booking has not ended
                        valid_bookings.append(booking)
                if len(valid_bookings) == 0:  # no bookings found for user/car
                    print("no valid bookings")
                    return Response("No valid bookings were found", status=404)
                elif len(valid_bookings) > 1:  # there can only be one valid booking for a user and car
                    print("multi booking error")
                    return Response("Multiple bookings found: database error", status=500)
                else:  # valid booking found, so details are updated
                    Car.query.get(car_id).locked = locked_val
                    db.session.commit()
                    message = "Successful: car is {}".format("locked" if locked_val == 1 else "unlocked")
                if locked_val == 1:  # if car is to be locked/returned
                    Booking.query.get(valid_bookings[0].booking_id).completed = 1
                    db.session.commit()
                    message = message + ", booking has been completed"
                return Response(message, status=200)
            else:
                print("no bookings")
                return Response("No bookings found - invalid parameters", status=404)
    return Response("Missing required params: car_id", status=400)


def update_location(car_id):
    """
    Updates the cars location coords in the db
    Args:
        car_id: id of car in db

    Returns:
        Corresponding response code: 200 if successful, 404 if missing car_id in table, or 400 for client error
    """
    long = request.args.get('long')
    lat = request.args.get('lat')
    if None not in (long, lat):
        car = Car.query.get(car_id)
        if car is not None:
            try:
                fl_long = float(long)
                fl_lat = float(lat)
                if fl_long > 180 or fl_long < -180:
                    raise ValueError("long {} outside valid bounds".format(fl_long))
                if fl_lat > 90 or fl_lat < -90:
                    raise ValueError("lat {}  outside valid bounds".format(fl_lat))
                car.lat = fl_lat
                car.long = fl_long
                db.session.commit()
                return Response("Updated coords: {} lat{},long{}".format(car_id, lat, long), status=200)
            except ValueError as ve:
                return Response("Invalid lat/long format: {}".format(str(ve)), status=400)
        return Response("Car not found, invalid id{}".format(car_id), status=404)
    else:
        return Response("Missing required params: lat, long", status=400)


@api.route("/cars/<start>/<end>", methods=['GET'])
def get_valid_cars(start, end):
    """
    Returns a list of cars that are able to be booked between desired dates
    Args:
        start: start datetime of booking
        end: end datetime of booking

    Returns:
        JSON object containing valid options for booking
    """
    bookings = Booking.query.filter_by(completed=0)
    data = json.loads(BookingSchema(many=True, exclude=['user.password']).dumps(bookings))
    booked_cars = []
    for booking in data:
        # TODO - check for conversion/datatype error
        b_start = datetime.strptime(booking['start'], "%Y-%m-%dT%H:%M:%S")
        b_end = datetime.strptime(booking['end'], "%Y-%m-%dT%H:%M:%S")
        start_dt = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S")
        end_dt = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S")
        if compare_dates(start=start_dt, end=end_dt, b_start=b_start, b_end=b_end):  # overlap found
            booked_cars.append(booking['car_id'])  # add to booked car list
    # get cars that don't match any cars with overlapping bookings
    cars = Car.query.filter(Car.car_id.notin_(booked_cars))
    return Response(CarSchema(many=True).dumps(cars), status=200, mimetype="application/json")


@api.route("/bookings", methods=['GET'])
def get_bookings():
    """
    Returns a list of bookings, optionally with user_id returns bookings for a user

    Returns:
        JSON object containing user bookings
    """
    user_id = request.args.get('user_id')
    if user_id is None:
        bookings = Booking.query.all()
    else:
        status = request.args.get('status')
        if status is not None:
            bookings = Booking.query.filter_by(completed=int(status)).join(User).filter(User.email == user_id)
        else:
            bookings = Booking.query.join(User).filter(User.email == user_id)
    return Response(
        BookingSchema(many=True, exclude=['user.password']).dumps(bookings), status=200, mimetype="application/json"
    )


@api.route("/booking", methods=['GET'])
def get_booking():
    """
    Returns a booking with booking id

    Returns:
        JSON object containing a booking
    """
    booking_id = request.args.get('booking_id')
    if booking_id is not None:
        booking = Booking.query.get(booking_id)
        if booking is not None:
            return Response(BookingSchema().dumps(booking), status=200, content_type="application/json")
        else:
            return Response("invalid booking id", status=404)
    return Response("missing booking_id argument", status=400)


@api.route("/booking", methods=['POST'])
def add_booking():
    """
    Adds a booking to the database

    Returns:
        JSON object with response code (successful/error)
    """
    request_data = request.get_json()
    if request_data is not None:
        data = json.loads(request_data)
        booking = Booking()
        booking.start = datetime.strptime(data['start'], "%Y-%m-%d %H:%M:%S")
        booking.end = datetime.strptime(data['end'], "%Y-%m-%d %H:%M:%S")
        booking.user_id = data['user_id']
        booking.car_id = data['car_id']
        booking.completed = 0
        if data['event_id'] is not None:
            booking.event_id = data['event_id']
        db.session.add(booking)
        db.session.commit()
        response = {
            "status_code": 200,
            "booking_id": booking.booking_id
        }
    else:
        response = Response(status=400)
    return response


@api.route("/booking", methods=['PUT'])
def update_booking():
    """
    Update booking status: cancelled or completed
    Returns:
        Success if processed correctly, otherwise error corresponding to the problem
    """
    data = request.get_json()
    print(data)
    response = {}
    if data is not None:
        json_data = json.loads(data)
        booking_id = json_data['booking_id']
        status = json_data['status']
        if None not in (status, booking_id):
            booking = Booking.query.get(booking_id)
            if booking is not None:
                booking.completed = int(status)
                db.session.commit()
                response['code'] = 'SUCCESS'
                response['data'] = {
                    'car_id': booking.car_id,
                    'start': booking.start,
                    'end': booking.end
                }
            else:
                response['code'] = 'BOOKING ERROR'
                response['data'] = 'Invalid BookingID'
    else:
        response['code'] = "JSON ERROR"
        response['data'] = 'Invalid JSON received.'
    return response


@api.route("/eventId", methods=['PUT'])
def update_eventId():
    """
    Update eventid for booking
    Returns:
        Success if processed correctly, otherwise error corresponding to the problem
    """
    data = request.get_json()
    print(data)
    response = {}
    if data is not None:
        json_data = json.loads(data)
        event_id = json_data['event_id']
        booking_id = json_data['booking_id']
        if None not in (event_id, booking_id):
            booking = Booking.query.get(booking_id)
            if booking is not None:
                booking.event_id = event_id
                db.session.commit()
                response['code'] = 'SUCCESS'
                response['data'] = {
                    'car_id': booking.car_id,
                    'start': booking.start,
                    'end': booking.end,
                    'event_id': booking.event_id
                }
            else:
                response['code'] = 'BOOKING ERROR'
                response['data'] = 'Invalid BookingID'
    else:
        response['code'] = "JSON ERROR"
        response['data'] = 'Invalid JSON received.'
    return response


@api.route("/populate", methods=['GET'])
def populate():
    """
    populates database on init with dummy data using csv files (see test_data)
    """
    response = {}
    if User.query.first() is None:
        # users
        user_cols = ['email', 'f_name', 'l_name', 'password']
        users = pd.read_csv('./test_data/user.csv', engine='python', sep=',', names=user_cols, error_bad_lines=False)
        for index, row in users.iterrows():
            print(row)
            user = User()
            user.email = row['email']
            user.f_name = row['f_name']
            user.l_name = row['l_name']
            user.password = row['password']
            db.session.add(user)
        db.session.commit()
        response['users'] = True
        # car models
        cm_cols = ['model_id', 'make', 'model', 'year', 'capacity', 'colour']
        models = pd.read_csv('./test_data/car_model.csv', engine='python', sep=',', names=cm_cols,
                             error_bad_lines=False)
        for index, row in models.iterrows():
            print(row)
            model = CarModel()
            model.id = row['model_id']
            model.make = row['make']
            model.model = row['model']
            model.year = row['year']
            model.capacity = row['capacity']
            model.colour = row['colour']
            db.session.add(model)
        response['models'] = True
        # cars (references car models)
        car_cols = ['car_id', 'name', 'cph', 'available']
        cars = pd.read_csv('./test_data/car.csv', engine='python', sep=',', names=car_cols, error_bad_lines=False)
        for index, row in cars.iterrows():
            print(row)
            car = Car()
            car.car_id = row['car_id']
            car.model_id = random.choice(models.model_id.unique().tolist())
            car.cph = row['cph']
            car.name = row['name']
            car.locked = 1
            db.session.add(car)
        response['cars'] = True
        # bookings
        book_cols = ['start', 'end']
        bookings = pd.read_csv('./test_data/booking.csv', engine='python', sep=',', names=book_cols,
                               error_bad_lines=False)
        for index, row in bookings.iterrows():
            print(row)
            booking = Booking()
            booking.user_id = "donald@gmail.com"
            booking.car_id = random.choice(cars.car_id.unique().tolist())
            booking.start = row['start']
            booking.end = row['end']
            booking.completed = 0
            db.session.add(booking)
        response['bookings'] = True
        db.session.commit()
    else:
        response['users'] = False
        response['models'] = False
        response['cars'] = False
        response['bookings'] = False
    return response
