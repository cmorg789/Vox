use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

/// A media room tracked by the SFU.
struct Room {
    room_id: u32,
    users: HashMap<u32, UserSession>,
}

/// A user's media session within a room.
struct UserSession {
    user_id: u32,
    token: String,
}

/// The Selective Forwarding Unit for QUIC media transport.
///
/// Manages QUIC listener, room state, and media packet forwarding.
/// Runs its own tokio runtime on a background thread so it doesn't
/// block the Python event loop.
#[pyclass]
struct SFU {
    bind_addr: String,
    rooms: Arc<Mutex<HashMap<u32, Room>>>,
    running: Arc<Mutex<bool>>,
}

#[pymethods]
impl SFU {
    /// Create a new SFU instance.
    ///
    /// Args:
    ///     bind: Address to bind the QUIC listener (e.g. "0.0.0.0:4443")
    #[new]
    fn new(bind: &str) -> Self {
        SFU {
            bind_addr: bind.to_string(),
            rooms: Arc::new(Mutex::new(HashMap::new())),
            running: Arc::new(Mutex::new(false)),
        }
    }

    /// Start the QUIC listener on a background thread.
    fn start(&self) -> PyResult<()> {
        let mut running = self.running.lock().unwrap();
        if *running {
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "SFU is already running",
            ));
        }
        *running = true;

        let bind_addr = self.bind_addr.clone();
        let rooms = Arc::clone(&self.rooms);

        std::thread::spawn(move || {
            let rt = tokio::runtime::Runtime::new().unwrap();
            rt.block_on(async move {
                tracing_subscriber::fmt::init();
                tracing::info!("SFU starting on {}", bind_addr);

                // TODO: set up quinn QUIC endpoint, accept connections,
                // authenticate via media_token, forward datagrams between
                // room participants based on SVC layer decisions
                let _ = rooms;
                loop {
                    tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
                }
            });
        });

        Ok(())
    }

    /// Stop the SFU.
    fn stop(&self) -> PyResult<()> {
        let mut running = self.running.lock().unwrap();
        *running = false;
        tracing::info!("SFU stopping");
        // TODO: signal the background runtime to shut down
        Ok(())
    }

    /// Create a new media room.
    fn add_room(&self, room_id: u32) -> PyResult<()> {
        let mut rooms = self.rooms.lock().unwrap();
        rooms.insert(
            room_id,
            Room {
                room_id,
                users: HashMap::new(),
            },
        );
        Ok(())
    }

    /// Remove a media room and disconnect all participants.
    fn remove_room(&self, room_id: u32) -> PyResult<()> {
        let mut rooms = self.rooms.lock().unwrap();
        rooms.remove(&room_id);
        Ok(())
    }

    /// Admit a user to a room with their media token.
    fn admit_user(&self, room_id: u32, user_id: u32, token: &str) -> PyResult<()> {
        let mut rooms = self.rooms.lock().unwrap();
        let room = rooms.get_mut(&room_id).ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Room {} does not exist",
                room_id
            ))
        })?;
        room.users.insert(
            user_id,
            UserSession {
                user_id,
                token: token.to_string(),
            },
        );
        Ok(())
    }

    /// Remove a user from a room.
    fn remove_user(&self, room_id: u32, user_id: u32) -> PyResult<()> {
        let mut rooms = self.rooms.lock().unwrap();
        if let Some(room) = rooms.get_mut(&room_id) {
            room.users.remove(&user_id);
        }
        Ok(())
    }

    /// Get the list of user IDs in a room.
    fn get_room_users(&self, room_id: u32) -> PyResult<Vec<u32>> {
        let rooms = self.rooms.lock().unwrap();
        let room = rooms.get(&room_id).ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Room {} does not exist",
                room_id
            ))
        })?;
        Ok(room.users.keys().cloned().collect())
    }
}

/// Python module definition.
#[pymodule]
fn vox_sfu(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<SFU>()?;
    Ok(())
}
