use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

pub type SharedState = Arc<RwLock<State>>;

pub struct State {
    pub rooms: HashMap<u32, Room>,
    pub token_index: HashMap<String, (u32, u32)>,
}

pub struct Room {
    pub room_id: u32,
    pub users: HashMap<u32, UserSession>,
}

pub struct UserSession {
    pub user_id: u32,
    pub token: String,
    pub connection: Option<quinn::Connection>,
}

impl State {
    pub fn new() -> Self {
        State {
            rooms: HashMap::new(),
            token_index: HashMap::new(),
        }
    }

    pub fn add_room(&mut self, room_id: u32) {
        self.rooms.entry(room_id).or_insert_with(|| Room {
            room_id,
            users: HashMap::new(),
        });
    }

    pub fn remove_room(&mut self, room_id: u32) {
        if let Some(room) = self.rooms.remove(&room_id) {
            for (_, session) in room.users {
                self.token_index.remove(&session.token);
            }
        }
    }

    pub fn admit_user(&mut self, room_id: u32, user_id: u32, token: &str) {
        self.token_index
            .insert(token.to_string(), (room_id, user_id));
        if let Some(room) = self.rooms.get_mut(&room_id) {
            room.users.insert(
                user_id,
                UserSession {
                    user_id,
                    token: token.to_string(),
                    connection: None,
                },
            );
        }
    }

    pub fn remove_user(&mut self, room_id: u32, user_id: u32) {
        if let Some(room) = self.rooms.get_mut(&room_id) {
            if let Some(session) = room.users.remove(&user_id) {
                self.token_index.remove(&session.token);
            }
        }
    }

    pub fn get_room_users(&self, room_id: u32) -> Option<Vec<u32>> {
        self.rooms
            .get(&room_id)
            .map(|room| room.users.keys().cloned().collect())
    }
}

pub fn new_shared() -> SharedState {
    Arc::new(RwLock::new(State::new()))
}
