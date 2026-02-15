mod endpoint;
mod header;
mod state;
mod tls;

use pyo3::prelude::*;
use tokio_util::sync::CancellationToken;

use state::SharedState;

/// The Selective Forwarding Unit for QUIC media transport.
///
/// Manages QUIC listener, room state, and media packet forwarding.
/// Runs its own tokio runtime on a background thread so it doesn't
/// block the Python event loop.
#[pyclass]
struct SFU {
    bind_addr: String,
    state: SharedState,
    cancel: Option<CancellationToken>,
    rt_handle: Option<std::thread::JoinHandle<()>>,
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
            state: state::new_shared(),
            cancel: None,
            rt_handle: None,
        }
    }

    /// Start the QUIC listener on a background thread.
    fn start(&mut self) -> PyResult<()> {
        if self.cancel.is_some() {
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "SFU is already running",
            ));
        }

        let cancel = CancellationToken::new();
        self.cancel = Some(cancel.clone());

        let bind_addr = self.bind_addr.clone();
        let state = self.state.clone();

        let handle = std::thread::spawn(move || {
            let rt = tokio::runtime::Runtime::new().unwrap();
            rt.block_on(async move {
                endpoint::run(bind_addr, state, cancel).await;
            });
        });

        self.rt_handle = Some(handle);
        Ok(())
    }

    /// Stop the SFU.
    fn stop(&mut self) -> PyResult<()> {
        if let Some(cancel) = self.cancel.take() {
            cancel.cancel();
        }
        if let Some(handle) = self.rt_handle.take() {
            let _ = handle.join();
        }
        tracing::info!("SFU stopped");
        Ok(())
    }

    /// Create a new media room.
    fn add_room(&self, room_id: u32) -> PyResult<()> {
        let mut st = self.state.blocking_write();
        st.add_room(room_id);
        Ok(())
    }

    /// Remove a media room and disconnect all participants.
    fn remove_room(&self, room_id: u32) -> PyResult<()> {
        let mut st = self.state.blocking_write();
        st.remove_room(room_id);
        Ok(())
    }

    /// Admit a user to a room with their media token.
    fn admit_user(&self, room_id: u32, user_id: u32, token: &str) -> PyResult<()> {
        let mut st = self.state.blocking_write();
        if !st.rooms.contains_key(&room_id) {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Room {} does not exist",
                room_id
            )));
        }
        st.admit_user(room_id, user_id, token);
        Ok(())
    }

    /// Remove a user from a room.
    fn remove_user(&self, room_id: u32, user_id: u32) -> PyResult<()> {
        let mut st = self.state.blocking_write();
        st.remove_user(room_id, user_id);
        Ok(())
    }

    /// Get the list of user IDs in a room.
    fn get_room_users(&self, room_id: u32) -> PyResult<Vec<u32>> {
        let st = self.state.blocking_read();
        st.get_room_users(room_id).ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Room {} does not exist",
                room_id
            ))
        })
    }
}

/// Python module definition.
#[pymodule]
fn vox_sfu(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<SFU>()?;
    Ok(())
}
