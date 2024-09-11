from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from example_models.users_model import Users
from zara.application.application import ASGIApplication, Request, Router
from zara.application.authentication import auth_required
from zara.application.events import Event
from zara.application.validation import Required, check_required_fields, validate
from zara.asgi.server import ASGIServer
from zara.errors import UnauthenticatedError
from zara.server.validation import BaseValidator
from zara.utilities.database import AsyncDatabase
from zara.utilities.dotenv import env
from zara.utilities.jwt_encode_decode import get_keycloak_token

SECRET_KEY = "your_application_secret"
ALGORITHM = "HS256"
CLIENT_ID = "local"
CLIENT_SECRET = "I3EUXRwR1W1fSz2ZYy7XZOnmKSn7uruK"  # If necessary
REDIRECT_URI = "http://localhost:8000/callback"

app = ASGIApplication()

router = Router()


# testing hot reload in doc
@dataclass
class RegisterValidator(BaseValidator):
    name: Required[str] = None
    receive_marketing: bool = False
    email: Optional[str] = None

    async def validate(self) -> List[Dict[str, Any]]:
        errors = []
        required_missing = check_required_fields(self)
        for field in required_missing:
            errors.append(
                {
                    "field": field,
                    "message": f"validationErrors.{field}IsMissing",
                }
            )
        if self.receive_marketing and not self.email:
            errors.append(
                {
                    "field": "email",
                    "message": "validationErrors.emailRequiredForMarketing",
                }
            )
        if self.email is not None:
            if "@" not in self.email or "." not in self.email:
                errors.append(
                    {
                        "field": "email",
                        "message": "validationErrors.emailInvalid",
                    }
                )
        return errors


app.add_router(router)


@router.get("/")
async def hello_world(request: Request):
    request.logger.warning(env.get("DATABASE_URL"))
    database = AsyncDatabase
    async with database("acme_corp", backend="postgresql") as db:
        try:
            user = await Users(name="John Smith", username="johnsmith", email_address="john@smith.site").create(db)
        except Exception as e:
            request.logger.error(str(e))
        print(f"Created user: {user}")
    return b"Hello, World! I just changed this file"


@router.post("/validate")
@validate(RegisterValidator)
async def validate(request: Request):
    return b"Valid!"


# Second router
router_two = Router(name="two")


app.add_router(router_two)


@router.post("/login")
async def login(request: Request):
    data = await request.json()
    request.logger.debug(data)
    username = data.get("username")
    password = data.get("password")
    # TODO: user table should delineate users that have OID connected in each schema
    internal_user = username != "internal_user"
    request.logger.debug(f"{username} username, {password} password")

    if not username or not password:
        return {"error": "Username and password are required"}, 400

    config = None
    if not internal_user:
        config = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "token_url": "http://localhost:8080/realms/master/protocol/openid-connect/token",
        }

    try:
        request.logger.debug(f"is internal: {internal_user}")
        token_response = await get_keycloak_token(
            username, password, endpoint_config=config
        )
        request.logger.debug(token_response)
        if "error" in token_response:
            return {"error": token_response["error_description"]}, 401
        request.set_cookie("refreshToken", token_response["refresh_token"])
        return {"access_token": token_response["access_token"], "token_type": "Bearer"}
    except Exception as e:
        if "401" in str(e):
            raise UnauthenticatedError()
        else:
            request.logger.error(e)


@router_two.get("/greet")
async def greet(request: Request):
    return b"Greetings!"


@router.post("/permit")
@auth_required(roles=["manage-account"])
async def permit(request: Request):
    return b"Permitted!"


async def after_request(event: Event):
    event.logger.debug(f"AfterRequest fired: {event.data}")


app.add_listener("AfterRequest", after_request)


async def on_scheduled_event(event: Event):
    event.logger.debug(f"OnScheduledEvent fired: {event.data}")


app.add_listener("OnScheduledEvent", on_scheduled_event)


server = ASGIServer(app)
server.run()
