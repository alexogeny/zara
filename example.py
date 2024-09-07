from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from zara.application.application import ASGIApplication, Request, Router
from zara.application.authentication import auth_required, get_keycloak_token
from zara.application.events import Event
from zara.application.validation import Required, check_required_fields, validate
from zara.asgi.server import ASGIServer
from zara.server.validation import BaseValidator

app = ASGIApplication()

router = Router()


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
    return b"Hello, World!"


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

    request.logger.debug(f"{username} username, {password} password")

    if not username or not password:
        return {"error": "Username and password are required"}, 400

    try:
        # Fetch token from Keycloak
        token_response = await get_keycloak_token(username, password)
        request.logger.debug(token_response)
        if "error" in token_response:
            return {"error": token_response["error_description"]}, 401

        # Return the access token (JWT)
        return {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get(
                "refresh_token"
            ),  # If you want to use refresh tokens
            "token_type": token_response["token_type"],
        }
    except Exception as e:
        return str(e).encode("utf-8")


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


server = ASGIServer(app, "127.0.0.1", 5000)
server.run()
