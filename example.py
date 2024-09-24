from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from example_models.users_model import User
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
from zara.errors import ForbiddenError, NotFoundError, UnauthenticatedError
from zara.utilities.database.models.configuration_model import (
    Configuration,
    OpenIDProvider,
)
from zara.utilities.database.models.public_model import (
    Configuration as PublicConfiguration,
)
from zara.utilities.jwt_encode_decode import (
    create_password,
    get_token_from_local_system,
    get_token_from_openid_provider,
)

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


@router.post("/user/create/{username:str}")
async def hello_world_create(request: Request, username: str):
    user = await User(
        name="John Smith",
        username=username,
        email_address="john@smith.site",
    ).create()
    tenant_entry, _ = await Configuration.first_or_create()
    tenant_secret = tenant_entry.token_secret
    public_entry, _ = await Configuration.first_or_create()
    public_secret = public_entry.token_secret
    password = create_password(
        "password", f"{public_secret}{tenant_secret}{user.token_secret}".encode("utf-8")
    )
    user.password_hash = password[0]
    await user.save()
    return user


@router.get("/user/{id:str}")
async def get_user(request: Request, id: str):
    user = await User.get(id=id)
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
    user = await User.get(username=data.get("username"))
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
    return openid_provider


@router.post("/update-user")
async def update_user(request: Request):
    data = await request.json()
    user = await User.get(username=data.get("username"))
    if not user:
        raise NotFoundError("User not found")
    if user.is_system:
        raise ForbiddenError("User is system")
    user.set(
        openid_username=data.get("openid_username"),
        openid_provider=data.get("openid_provider"),
    )
    await user.save()
    return user


@router.post("/login")
async def login(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return {"error": "Username and password are required"}, 400
    request.logger.error(f"username: {username}")
    user = await User.get(username=username)
    if not user:
        return {"error": "User not found"}, 404
    request.logger.error(f"user: {user}")
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
            token_response = await get_token_from_openid_provider(
                user.openid_username or username,
                password,
                request.logger,
                endpoint_config=config,
            )
            if "error" in token_response:
                return {"error": token_response["error_description"]}, 401
            request.set_cookie("refreshToken", token_response["refresh_token"])
            return {
                "access_token": token_response["access_token"],
                "token_type": "Bearer",
            }
        except Exception as e:
            if "401" in str(e):
                raise UnauthenticatedError()
            else:
                raise e
    else:
        request.logger.error(f"user is system: {user.is_system}")
        tenant_config = await Configuration.first()
        request.logger.error(f"tenant config: {tenant_config}")
        public_config = await PublicConfiguration.first()
        request.logger.error(f"tenant config: {tenant_config}")
        request.logger.error(f"public config: {public_config}")
        request.logger.error(f"user: {user}")
        token_response = await get_token_from_local_system(
            password,
            user,
            tenant_secret=tenant_config.token_secret,
            public_secret=public_config.token_secret,
        )
        if "access_token" not in token_response:
            raise UnauthenticatedError()
        await user.sessions.create(
            token=token_response["access_token"],
            expires_at=token_response["expires_in"],
            refresh_token=token_response["refresh_token"],
            ip_address=request.headers.get(b"X-Real-IP"),
            user_agent=request.headers.get(b"User-Agent"),
        )
        return token_response


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
