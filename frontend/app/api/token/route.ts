import { NextResponse } from 'next/server';
import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';
import { RoomConfiguration } from '@livekit/protocol';

type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

// NOTE: you are expected to define the following environment variables in `.env.local`:
const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;
const AGENT_NAME = process.env.AGENT_NAME;

// don't cache the results
export const revalidate = 0;

/** Must match `CALLER_ID_PREFIX` in lib/caller-id.ts and backend/src/agent.py. */
const CALLER_ID_PREFIX = 'sehat-caller-';
const CALLER_ID_PATTERN = new RegExp(`^${CALLER_ID_PREFIX}[A-Za-z0-9-]{8,64}$`);

/**
 * The caller id from the request, if it is one we would have issued.
 *
 * This value becomes a LiveKit participant identity and the key to a caller's
 * stored health facts, and it arrives from the client, so it is validated
 * rather than trusted: exact prefix, bounded length, and no characters beyond
 * those a UUID uses. Anything else is discarded and the caller gets a throwaway
 * identity instead.
 *
 * This does not make the id unforgeable — anyone who knows someone else's id
 * could send it. Real protection needs an authenticated caller, which is a
 * telephony or sign-in problem rather than a token-route one. It is why the
 * agent still confirms who it is speaking to out loud before it acts on what it
 * remembers.
 *
 * The SDK's casing for this field has varied, so both spellings are accepted.
 */
function callerIdFrom(body: Record<string, unknown>): string | undefined {
  const candidate = body?.participantIdentity ?? body?.participant_identity;
  if (typeof candidate !== 'string') return undefined;
  return CALLER_ID_PATTERN.test(candidate) ? candidate : undefined;
}

export async function POST(req: Request) {
  try {
    if (LIVEKIT_URL === undefined) {
      throw new Error('LIVEKIT_URL is not defined');
    }
    if (API_KEY === undefined) {
      throw new Error('LIVEKIT_API_KEY is not defined');
    }
    if (API_SECRET === undefined) {
      throw new Error('LIVEKIT_API_SECRET is not defined');
    }

    // Parse room config from request body (if provided).
    const body = await req.json().catch(() => ({}));
    let roomConfig: RoomConfiguration | undefined;
    if (body?.room_config) {
      roomConfig = RoomConfiguration.fromJson(body.room_config, { ignoreUnknownFields: true });
    } else if (AGENT_NAME) {
      // When AGENT_NAME is set, configure explicit agent dispatch so the named
      // agent worker picks up the job when a user joins the room.
      roomConfig = RoomConfiguration.fromJson(
        { agents: [{ agentName: AGENT_NAME }] },
        { ignoreUnknownFields: true }
      );
    }

    // Generate participant token
    const participantName = 'user';
    // A caller who has been here before sends the id their browser kept, and the
    // agent uses it to look up what it may remember. Without it — private
    // browsing, a first visit, storage blocked — they get a throwaway identity
    // and the agent treats them as new, which is the correct default.
    const participantIdentity =
      callerIdFrom(body) ?? `voice_assistant_user_${Math.floor(Math.random() * 10_000)}`;
    const roomName = `voice_assistant_room_${Math.floor(Math.random() * 10_000)}`;

    const participantToken = await createParticipantToken(
      { identity: participantIdentity, name: participantName },
      roomName,
      roomConfig
    );

    // Return connection details
    const data: ConnectionDetails = {
      serverUrl: LIVEKIT_URL,
      roomName,
      participantName,
      participantToken,
    };
    const headers = new Headers({
      'Cache-Control': 'no-store',
    });
    return NextResponse.json(data, { headers });
  } catch (error) {
    if (error instanceof Error) {
      console.error(error);
      return new NextResponse(error.message, { status: 500 });
    }
  }
}

function createParticipantToken(
  userInfo: AccessTokenOptions,
  roomName: string,
  roomConfig?: RoomConfiguration
): Promise<string> {
  const at = new AccessToken(API_KEY, API_SECRET, {
    ...userInfo,
    ttl: '15m',
  });
  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  };
  at.addGrant(grant);

  if (roomConfig) {
    at.roomConfig = roomConfig;
  }

  return at.toJwt();
}
