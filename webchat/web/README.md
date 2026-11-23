# Web client

React + TypeScript (Vite). It talks only to `contracts/openapi.yaml` and `contracts/asyncapi.yaml`,
never to a service's internals.

## Screens

| Screen | Uses |
|---|---|
| Login / register | `POST /auth/login`, `POST /auth/register` |
| People | `GET /users/by-username/{username}`, friend requests, friends |
| Conversations | `GET /conversations`, `PUT /conversations/direct/{id}`, group creation |
| Chat | history, search, read-state, attachments, WebSocket |
| Summary | `POST /conversations/{id}/unread-summary` |

## Reconnect rule

Buffer `message.created` from the moment `conversation.subscribe` is sent. On
`conversation.subscribed`, fetch `after_seq=<synced>&through_seq=<latest_seq>` until `has_more=false`,
merge both sets by `message.id`, then render sorted by `seq`. The device sync marker and the user's
read marker are separate values.

## TTS rule

Only a new `message.created` from another user, in the open conversation, while the toggle is on,
enters the speech queue. ACKs, replays, own messages, history and search results never do. Leaving the
conversation cancels the queue and stops the current audio.

## Commands

```bash
npm ci
npm run dev
npm run lint
npm test -- --run
npm run build
```
