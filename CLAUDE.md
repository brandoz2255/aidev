# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the Jarvis Project, a sophisticated AI voice assistant that combines Next.js frontend with Python backend services. The project features voice-first interaction, browser automation, AI-powered coding assistance, and authentication with PostgreSQL.

## Key Commands

### Frontend Development (jfrontend)
- `cd front_end/jfrontend` - Navigate to the main frontend directory
- `npm run dev` - Start development server (runs on port 3000)
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint
- `npm run type-check` - Run TypeScript type checking

### Docker Operations
- `docker-compose up --build -d` - Build and run the entire stack
- `docker-compose down` - Stop all services
- `docker-compose logs -f [service]` - View logs for specific service

### Database Operations
- Database setup script: `front_end/jfrontend/db_setup.sql`
- PostgreSQL runs on port 5432 in container
- Uses environment variables from `.env.local`

## Architecture Overview

### Frontend (Next.js)
- **Location**: `front_end/jfrontend/`
- **Framework**: Next.js 14 with App Router
- **Styling**: Tailwind CSS with Radix UI components
- **State Management**: Zustand for chat state
- **Authentication**: JWT-based with bcrypt password hashing

### Backend Services
- **Python Backend**: `python_back_end/` - Main AI processing, voice controls, browser automation
- **REST API**: `rest_api/` - Additional API services
- **Database**: PostgreSQL with connection pooling

### Key Frontend Directories
- `app/` - Next.js app router pages and API routes
- `components/` - Reusable React components including UI components
- `lib/` - Utility functions, database connection, and authentication services
- `stores/` - Zustand state management
- `rag_context/` - RAG context documentation

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    avatar VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Authentication Architecture

### Recommended Approach: Backend-Centric Authentication (Most Secure)

**Current Status**: Authentication is currently handled by the Next.js frontend API routes. For maximum security, consider migrating to Python backend authentication.

### Option 1: Python Backend Authentication (RECOMMENDED - Most Secure)
- **Location**: Add auth endpoints to `python_back_end/main.py`
- **Database**: Direct PostgreSQL connection from Python using `psycopg2` or `asyncpg`
- **Security Benefits**:
  - Server-side password hashing with bcrypt
  - JWT token generation and validation on backend
  - Database queries isolated from frontend
  - Protection against client-side manipulation
  - Centralized auth logic for all AI services

### Option 2: Frontend API Routes (Current Implementation)
- **Location**: `front_end/jfrontend/app/api/auth/`
- **Database**: Uses `pg` library with connection pooling
- **Security**: Good but less secure than backend auth
- **Current Flow**:
  1. User signup/login through `/api/auth/login` or `/api/auth/signup`
  2. Passwords hashed with bcrypt
  3. JWT tokens generated with 1-hour expiration
  4. Token verification handled by `/api/me` endpoint

### Migration Path (Frontend → Backend Auth)
1. Create Python auth endpoints in `python_back_end/main.py`:
   - `POST /api/auth/login`
   - `POST /api/auth/signup`
   - `GET /api/auth/me`
2. Update frontend to call Python backend auth endpoints
3. Move database schema setup to Python backend
4. Update environment variables for backend database connection

## AI Integration

### Core AI Components
- **Voice Processing**: Whisper STT, Chatterbox TTS
- **LLM Integration**: Ollama for local model hosting
- **Browser Automation**: Selenium WebDriver
- **Screen Analysis**: Blip AI for visual understanding
- **Web Search**: LangChain-based web search with DuckDuckGo integration

### Key AI Features
- **Vibe Coding**: AI-powered development environment at `python_back_end/ollama_cli/vibe_agent.py`
- **Real-time Screen Analysis**: Context-aware assistance
- **Voice-First Interaction**: Natural language commands
- **Browser Automation**: Web navigation and interaction
- **Research & Web Search**: Comprehensive web search and research capabilities

### Web Search & Research API Endpoints

#### `/api/web-search` - Basic Web Search
**POST** - Perform web search using LangChain search agents

**Request Body:**
```json
{
  "query": "search query",
  "max_results": 5,
  "extract_content": false
}
```

**Response:**
```json
{
  "query": "search query",
  "search_results": [
    {
      "title": "Result Title",
      "url": "https://example.com",
      "snippet": "Result snippet",
      "source": "DuckDuckGo"
    }
  ],
  "extracted_content": []
}
```

#### `/api/research-chat` - Enhanced Research Chat
**POST** - Enhanced research with comprehensive web search and analysis

**Request Body:**
```json
{
  "message": "research question",
  "history": [],
  "model": "mistral",
  "enableWebSearch": true
}
```

#### `/api/fact-check` - Fact Checking
**POST** - Fact-check claims using web search

**Request Body:**
```json
{
  "claim": "claim to verify",
  "model": "mistral"
}
```

#### `/api/comparative-research` - Comparative Analysis
**POST** - Compare multiple topics using web research

**Request Body:**
```json
{
  "topics": ["topic1", "topic2"],
  "model": "mistral"
}
```

### Web Search Implementation Details

#### Search Agents
- **Location**: `python_back_end/research/`
- **Primary**: DuckDuckGo search via LangChain
- **Fallback**: Tavily API (requires `TAVILY_API_KEY`)
- **Content Extraction**: newspaper3k for full article content

#### Dependencies
Required packages in `requirements.txt`:
```
langchain
langchain-community
duckduckgo-search
beautifulsoup4
newspaper3k
tavily-python
```

### Troubleshooting Web Search

#### Common Issues with 0 Results

1. **Rate Limiting**: DuckDuckGo may throttle requests
   - **Solution**: Add delays between requests
   - **Check**: Look for rate limit errors in logs

2. **Network Issues in Docker**: Container connectivity problems
   - **Solution**: Verify Docker network configuration
   - **Check**: Test network connectivity from container

3. **User-Agent Blocking**: Search engines blocking requests
   - **Solution**: Set proper User-Agent (automatically configured)
   - **Environment**: `USER_AGENT` is set automatically if missing

4. **API Changes**: DuckDuckGo search library changes
   - **Warning**: Library suggests using `ddgs` instead of `duckduckgo_search`
   - **Solution**: Consider updating to newer library version

#### Debugging Steps

1. **Enable Debug Logging**: Set logging level to DEBUG
2. **Check Raw Results**: Verify DuckDuckGo returns data
3. **Network Tests**: Test connectivity from container
4. **Rate Limit Checks**: Monitor for rate limiting messages

#### Log Analysis
The web search endpoint provides detailed logging:
- Request parameters and query
- DuckDuckGo response count
- Formatted result details
- Error messages with full stack traces

Example log output:
```
INFO:main:Web search request: query='python', max_results=5, extract_content=False
INFO:research.web_search:Starting DuckDuckGo search for query: 'python' with max_results: 5
INFO:research.web_search:DuckDuckGo returned 5 raw results
INFO:main:Search completed: found 5 results
```

## Development Workflow

### Frontend Development
1. Navigate to `front_end/jfrontend/`
2. Install dependencies: `npm install`
3. Set up environment variables in `.env.local`
4. Run development server: `npm run dev`
5. Always run `npm run type-check` before committing

### Authentication Development

#### Current Frontend Implementation
- AuthService: `lib/auth/AuthService.ts` - Client-side auth functions
- UserProvider: `lib/auth/UserProvider.tsx` - Auth context provider
- Database connection: `lib/db.ts` - PostgreSQL connection pool

#### For Backend Authentication Migration
- Add auth dependencies to `python_back_end/requirements.txt`:
  ```
  python-jose[cryptography]
  passlib[bcrypt]
  python-multipart
  asyncpg
  ```
- Create auth middleware for protecting AI endpoints
- Update frontend AuthService to call backend endpoints
- Implement JWT token validation in Python backend

### Component Development
- UI components use Radix UI primitives
- Styling with Tailwind CSS
- Follow existing component patterns in `components/ui/`

## Docker Configuration

### Services
- **frontend**: Next.js app (port 3001 → 3000)
- **pgsql**: PostgreSQL database with health checks
- **Networks**: Uses external `ollama-n8n-network`

### Environment Variables
Required in `.env.local`:
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET` - JWT signing secret
- `BACKEND_URL` - Backend service URL (default: http://backend:8000)

For backend authentication, also add to Python backend environment:
- `DATABASE_URL` - PostgreSQL connection for Python backend
- `JWT_SECRET` - Same secret for token validation consistency
- `JWT_ALGORITHM` - JWT algorithm (default: HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiration (default: 60)

## Common Issues

### Database Connection
- Ensure PostgreSQL service is healthy before frontend starts
- Check `DATABASE_URL` environment variable
- Verify network connectivity between services

### Authentication
- JWT tokens expire after 1 hour (configurable)
- Password hashing uses bcrypt
- Check JWT_SECRET is properly set and consistent between frontend/backend
- For backend auth: Ensure Python backend can connect to PostgreSQL
- Token validation should be consistent across all services

### Type Checking
- Run `npm run type-check` regularly
- TypeScript errors are ignored in builds (not recommended for production)

## Git Branch Strategy
- Main branch: `main`
- Feature branches: Create from `main`
- Use conventional commits: `feat:`, `fix:`, `docs:`, etc.

## Testing
- No specific test framework configured
- Manual testing recommended for auth flows
- Test database operations with PostgreSQL running

## Security Considerations

### Current Security (Frontend Auth)
- Passwords are hashed with bcrypt
- JWT tokens for authentication
- Environment variables for sensitive data
- Database connection uses connection pooling
- Frontend runs in standalone mode for Docker deployment

### Enhanced Security (Backend Auth - Recommended)
- **Authentication Logic**: Move all auth logic to Python backend
- **Database Access**: Direct backend-to-database connection (no frontend DB access)
- **Token Validation**: Centralized JWT validation in Python backend
- **API Protection**: Protect all AI endpoints with auth middleware
- **CORS Configuration**: Properly configure CORS for frontend-backend communication
- **Input Validation**: Server-side validation of all auth inputs
- **Rate Limiting**: Implement rate limiting on auth endpoints
- **Audit Logging**: Log all authentication attempts and API access

### Security Benefits of Backend Auth
1. **Reduced Attack Surface**: Auth logic not exposed to client-side
2. **Centralized Security**: All AI services protected by same auth system
3. **Database Security**: Direct backend-to-database connection
4. **Token Security**: JWT secrets never exposed to frontend
5. **Consistent Validation**: Same auth validation across all endpoints