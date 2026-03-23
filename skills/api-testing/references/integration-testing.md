# Integration Testing

## API Testing (Supertest)

```typescript
import request from 'supertest';
import { app } from '../app';

describe('POST /api/users', () => {
  it('creates user with valid data', async () => {
    const response = await request(app)
      .post('/api/users')
      .send({ email: 'test@test.com', name: 'Test' })
      .expect(201);

    expect(response.body).toMatchObject({
      email: 'test@test.com',
      name: 'Test',
    });
    expect(response.body.id).toBeDefined();
  });

  it('returns 400 for invalid email', async () => {
    const response = await request(app)
      .post('/api/users')
      .send({ email: 'invalid', name: 'Test' })
      .expect(400);

    expect(response.body.error).toContain('email');
  });

  it('returns 401 without auth token', async () => {
    await request(app)
      .get('/api/users/me')
      .expect(401);
  });
});
```

## Authenticated Requests

```typescript
describe('Protected endpoints', () => {
  let authToken: string;

  beforeAll(async () => {
    const response = await request(app)
      .post('/api/auth/login')
      .send({ email: 'test@test.com', password: 'password' });
    authToken = response.body.token;
  });

  it('accesses protected route', async () => {
    await request(app)
      .get('/api/users/me')
      .set('Authorization', `Bearer ${authToken}`)
      .expect(200);
  });
});
```

## Database Testing

```typescript
import { db } from '../database';

describe('UserRepository', () => {
  beforeEach(async () => {
    await db.query('DELETE FROM users');
  });

  afterAll(async () => {
    await db.end();
  });

  it('creates and retrieves user', async () => {
    const user = await userRepo.create({
      email: 'test@test.com',
      name: 'Test',
    });

    const found = await userRepo.findById(user.id);
    expect(found).toEqual(user);
  });
});
```

## pytest API Testing

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    response = await client.post("/api/users/", json={
        "email": "test@example.com",
        "name": "Test"
    })
    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"

@pytest.mark.asyncio
async def test_invalid_email(client: AsyncClient):
    response = await client.post("/api/users/", json={
        "email": "invalid",
        "name": "Test"
    })
    assert response.status_code == 422
```

## Spring Boot Test (Java)

```java
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.context.ActiveProfiles;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.hamcrest.Matchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class UserControllerIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @BeforeEach
    void setUp() {
        userRepository.deleteAll();
    }

    @Test
    @DisplayName("POST /api/users - creates user with valid data")
    void createUser_withValidData_returns201() throws Exception {
        String requestBody = """
            {
                "email": "test@example.com",
                "name": "Test User"
            }
            """;

        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.email").value("test@example.com"))
            .andExpect(jsonPath("$.name").value("Test User"))
            .andExpect(jsonPath("$.id").exists());
    }

    @Test
    @DisplayName("POST /api/users - returns 400 for invalid email")
    void createUser_withInvalidEmail_returns400() throws Exception {
        String requestBody = """
            {
                "email": "invalid",
                "name": "Test User"
            }
            """;

        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[?(@.field == 'email')]").exists());
    }

    @Test
    @DisplayName("GET /api/users/me - returns 401 without auth token")
    void getCurrentUser_withoutAuth_returns401() throws Exception {
        mockMvc.perform(get("/api/users/me"))
            .andExpect(status().isUnauthorized());
    }
}
```

### Authenticated Requests (Spring Boot)

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProtectedEndpointTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtUtil jwtUtil;

    private String authToken;

    @BeforeEach
    void setUp() {
        User testUser = new User("test@example.com", "Test User");
        authToken = jwtUtil.generateToken(testUser);
    }

    @Test
    @DisplayName("GET /api/users/me - returns current user with valid token")
    void getCurrentUser_withValidToken_returnsUser() throws Exception {
        mockMvc.perform(get("/api/users/me")
                .header("Authorization", "Bearer " + authToken))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.email").value("test@example.com"));
    }

    @Test
    @DisplayName("GET /api/users/me - returns 401 with expired token")
    void getCurrentUser_withExpiredToken_returns401() throws Exception {
        String expiredToken = jwtUtil.generateExpiredToken();

        mockMvc.perform(get("/api/users/me")
                .header("Authorization", "Bearer " + expiredToken))
            .andExpect(status().isUnauthorized());
    }
}
```

### Database Testing with TestContainers

```java
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
@ActiveProfiles("test")
class UserRepositoryIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:15-alpine");

    @DynamicPropertySource
    static void configureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private UserRepository userRepository;

    @Test
    @DisplayName("creates and retrieves user")
    void createAndRetrieveUser() {
        User user = new User("test@example.com", "Test User");
        User saved = userRepository.save(user);

        User found = userRepository.findById(saved.getId()).orElseThrow();

        assertThat(found.getEmail()).isEqualTo("test@example.com");
        assertThat(found.getName()).isEqualTo("Test User");
    }
}
```

## REST Assured (Java)

```java
import io.restassured.RestAssured;
import io.restassured.response.Response;
import io.restassured.specification.RequestSpecification;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static io.restassured.RestAssured.*;
import static org.hamcrest.Matchers.*;

class UserApiTest {

    @BeforeAll
    static void setup() {
        RestAssured.baseURI = "http://localhost";
        RestAssured.port = 8080;
        RestAssured.basePath = "/api";
    }

    @Test
    void createUser_withValidData_returns201() {
        String requestBody = """
            {
                "email": "test@example.com",
                "name": "Test User"
            }
            """;

        given()
            .contentType("application/json")
            .body(requestBody)
        .when()
            .post("/users")
        .then()
            .statusCode(201)
            .body("email", equalTo("test@example.com"))
            .body("name", equalTo("Test User"))
            .body("id", notNullValue());
    }

    @Test
    void createUser_withInvalidEmail_returns400() {
        String requestBody = """
            {
                "email": "invalid",
                "name": "Test User"
            }
            """;

        given()
            .contentType("application/json")
            .body(requestBody)
        .when()
            .post("/users")
        .then()
            .statusCode(400)
            .body("errors.find { it.field == 'email' }", notNullValue());
    }

    @Test
    void getCurrentUser_withoutAuth_returns401() {
        when()
            .get("/users/me")
        .then()
            .statusCode(401);
    }
}
```

### REST Assured with Authentication

```java
class AuthenticatedApiTest {

    private String authToken;

    @BeforeEach
    void login() {
        String loginBody = """
            {
                "email": "test@example.com",
                "password": "password123"
            }
            """;

        authToken = given()
            .contentType("application/json")
            .body(loginBody)
        .when()
            .post("/auth/login")
        .then()
            .statusCode(200)
            .extract()
            .path("token");
    }

    @Test
    void getProtectedResource_withAuth_returns200() {
        given()
            .header("Authorization", "Bearer " + authToken)
        .when()
            .get("/users/me")
        .then()
            .statusCode(200)
            .body("email", equalTo("test@example.com"));
    }

    @Test
    void getProtectedResource_withoutAuth_returns401() {
        when()
            .get("/users/me")
        .then()
            .statusCode(401);
    }
}
```

### REST Assured Advanced Patterns

```java
class AdvancedApiTest {

    private RequestSpecification requestSpec;

    @BeforeAll
    static void setup() {
        RequestSpecBuilder builder = new RequestSpecBuilder();
        builder.setBaseUri("http://localhost:8080");
        builder.setBasePath("/api");
        builder.setContentType("application/json");
        builder.addHeader("X-Api-Version", "1.0");
        requestSpec = builder.build();
    }

    @Test
    void testWithSpec() {
        given()
            .spec(requestSpec)
            .body("{\"name\": \"Test\"}")
        .when()
            .post("/users")
        .then()
            .spec(responseSpec(201));
    }

    @Test
    void extractResponseData() {
        User user = given()
            .contentType("application/json")
            .body("{\"email\": \"test@example.com\", \"name\": \"Test\"}")
        .when()
            .post("/users")
        .then()
            .statusCode(201)
            .extract()
            .as(User.class);

        assertThat(user.getEmail()).isEqualTo("test@example.com");
    }

    @Test
    void validateResponseTime() {
        given()
        .when()
            .get("/users")
        .then()
            .statusCode(200)
            .time(lessThan(2000L)); // Response time < 2 seconds
    }

    @Test
    void validateResponseHeaders() {
        given()
        .when()
            .get("/users")
        .then()
            .statusCode(200)
            .header("Content-Type", containsString("application/json"))
            .header("X-Total-Count", notNullValue());
    }
}
```

## Quick Reference

### JavaScript/TypeScript (Supertest)

| Method | Purpose |
|--------|---------|
| `.send(body)` | Send request body |
| `.set(header, value)` | Set header |
| `.expect(status)` | Assert status code |
| `.expect('Content-Type', /json/)` | Assert header |
| `response.body` | Parsed JSON body |

### Python (pytest + httpx)

| Method | Purpose |
|--------|---------|
| `client.post(url, json=data)` | POST request with JSON |
| `client.get(url)` | GET request |
| `response.status_code` | HTTP status code |
| `response.json()` | Parsed JSON body |

### Java (Spring Boot Test)

| Method | Purpose |
|--------|---------|
| `mockMvc.perform(get(url))` | Perform GET request |
| `.contentType(MediaType)` | Set content type |
| `.content(json)` | Set request body |
| `.andExpect(status().isOk())` | Assert status code |
| `.andExpect(jsonPath("$.field"))` | Assert JSON field |

### Java (REST Assured)

| Method | Purpose |
|--------|---------|
| `given().body(obj)` | Set request body |
| `.when().post(url)` | Perform POST request |
| `.then().statusCode(code)` | Assert status code |
| `.body("path", matcher)` | Assert JSON response |
| `.extract().as(Class)` | Deserialize response |
