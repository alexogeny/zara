from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from example_models.users_model import Users
from zara.application.application import ASGIApplication, Request, Router
from zara.application.authentication import auth_required
from zara.application.events import Event
from zara.application.validation import (
    Required,
    ValidatorBase,
    check_required_fields,
    validate,
)
from zara.asgi.server import ASGIServer
from zara.errors import UnauthenticatedError
from zara.utilities.database.models.configuration_model import OpenIDProvider
from zara.utilities.jwt_encode_decode import get_keycloak_token

SECRET_KEY = "your_application_secret"
ALGORITHM = "HS256"
CLIENT_ID = "local"
CLIENT_SECRET = "I3EUXRwR1W1fSz2ZYy7XZOnmKSn7uruK"  # If necessary
REDIRECT_URI = "http://localhost:8000/callback"

app = ASGIApplication()

router = Router()


@dataclass
class RegisterValidator(ValidatorBase):
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
                    "message": f"validationErrors.{field}Missing",
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
    return b"Hello, World!"


@router.get("/{username:str}")
async def hello_world_create(request: Request, username: str):
    user = await Users(
        name="John Smith", username=username, email_address="john@smith.site"
    ).create()
    request.logger.debug(f"Created user: {user}")
    return user


@router.get("/user/{id:str}")
async def get_user(request: Request, id: str):
    user = await Users.get(id=id)
    return user


@router.post("/validate")
@validate(RegisterValidator)
async def validate(request: Request):
    return b"Valid!"


# Second router
router_two = Router(name="two", prefix="/two")


app.add_router(router_two)


@router.post("/create-openid-provider")
async def create_openid_provider(request: Request):
    data = await request.json()
    user = await Users.get(username=data.get("username"))
    if not user:
        return {"error": "User not found"}, 404
    if user.is_system:
        return {"error": "User is system"}, 403
    openid_provider = OpenIDProvider(
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        redirect_uri=data.get("redirect_uri"),
        scope=data.get("scope"),
        issuer=data.get("issuer"),
        is_active=True,
    )

    await openid_provider.create()
    return openid_provider.as_dict()


@router.post("/update-user")
async def update_user(request: Request):
    data = await request.json()
    user = await Users.get(username=data.get("username"))
    if not user:
        return {"error": "User not found"}, 404
    if user.is_system:
        return {"error": "User is system"}, 403
    user.set(
        openid_username=data.get("openid_username"),
        openid_provider=data.get("openid_provider"),
    )
    await user.save()
    return user.as_dict()


@router.post("/login")
async def login(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return {"error": "Username and password are required"}, 400
    user = await Users.get(username=username)
    if not user:
        return {"error": "User not found"}, 404

    config = None
    if not user.is_system and user.openid_provider is not None:
        openid_provider = await OpenIDProvider.get(id=user.openid_provider)
        config = {
            "client_id": openid_provider.client_id,
            "client_secret": openid_provider.client_secret,
            "redirect_uri": openid_provider.redirect_uri,
            "token_url": openid_provider.issuer.replace("localhost", "keycloak"),
        }

    try:
        token_response = await get_keycloak_token(
            user.openid_username or username,
            password,
            request.logger,
            endpoint_config=config,
        )
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
