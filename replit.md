# MDM System - Project Overview

## Current Status
Production-ready cloud-based Mobile Device Management system with async PostgreSQL backend and Next.js frontend.

## Architecture
- **Backend**: FastAPI with async SQLAlchemy and PostgreSQL (optimized for 100+ concurrent devices)
- **Frontend**: Next.js with shadcn/ui components (ready for Vercel deployment)
- **Database**: PostgreSQL with connection pooling and 2-day event retention
- **Real-time**: WebSocket support for live device updates
- **Authentication**: JWT tokens with password reset via email

## Recent Changes (October 16, 2025)
- ✅ Set up PostgreSQL database with async SQLAlchemy
- ✅ Created high-performance FastAPI backend with async endpoints
- ✅ Implemented WebSocket manager for real-time communication
- ✅ Added comprehensive password reset system (email + admin tokens)
- ✅ Configured deployment for Replit (backend) and Vercel (frontend)
- ✅ Set up connection pooling for 100+ concurrent devices
- ✅ Implemented 2-day data retention for device logs
- ✅ Added rate limiting and security measures

## Project Structure
```
/
├── server/                 # FastAPI Backend
│   ├── main.py            # Main application with async endpoints
│   ├── database.py        # Async database configuration
│   ├── models_async.py    # SQLAlchemy async models
│   ├── auth.py            # Authentication utilities
│   ├── email_service.py   # Email service (Replit Mail)
│   └── websocket_manager.py # WebSocket connection handling
├── frontend/              # Next.js Frontend
│   ├── app/              # App directory
│   ├── components/       # React components
│   └── lib/             # Utilities
├── UNITYmdm/            # Original MDM codebase
└── requirements.txt     # Python dependencies
```

## Key Features Implemented
1. **Device Management**
   - Real-time heartbeat monitoring
   - Battery and memory tracking
   - Remote command execution
   - Auto-relaunch capability
   - Offline detection alerts

2. **Security**
   - JWT authentication
   - Password reset via email
   - Admin token generation
   - Rate limiting (3 requests/hour for password reset)
   - IP tracking for audit

3. **Performance Optimizations**
   - Connection pooling (20 base + 40 overflow)
   - Async database operations
   - Indexed queries
   - Background cleanup tasks
   - WebSocket message queuing

4. **Deployment**
   - Auto-scaling on Replit
   - PostgreSQL with automatic backups
   - Environment variable management
   - Production-ready configuration

## User Preferences
- Focus on scalability and performance
- Clean, maintainable code structure
- Comprehensive error handling
- Real-time updates via WebSockets
- Email notifications for critical events

## Technical Decisions
- **Async SQLAlchemy**: Chosen for non-blocking I/O and better concurrency
- **Connection Pooling**: Configured for 100+ simultaneous device connections
- **WebSocket Architecture**: Centralized manager for efficient connection handling
- **Event Retention**: 2-day retention with automatic cleanup
- **Rate Limiting**: IP-based with configurable windows

## Deployment Status
- **Backend**: Running on port 8000 (Replit)
- **Database**: PostgreSQL configured and running
- **Frontend**: Ready for Vercel deployment
- **Environment**: All secrets configured

## Next Steps
1. Deploy frontend to Vercel
2. Configure production domain
3. Set up monitoring and alerts
4. Test with 100+ devices
5. Enable production logging

## Important URLs
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/api/docs
- WebSocket Endpoint: ws://localhost:8000/ws/{device_id}
- Health Check: http://localhost:8000/api/health

## Credentials (Development)
- Default admin key: Set in environment variables
- JWT Secret: Auto-generated (change in production)
- Database: Auto-configured via Replit

## Performance Metrics
- Target: 100+ concurrent devices
- Heartbeat interval: 5 minutes
- Event retention: 2 days
- Connection pool: 60 total connections
- Rate limits: 60 req/min general, 3 req/hour password reset