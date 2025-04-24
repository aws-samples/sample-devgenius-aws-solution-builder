const AWS = require('aws-sdk');

const name = "cognitoClientSecrets";
const primarySecretManager = new AWS.SecretsManager({
  region: 'us-west-2',
});


const getSecrets = async () => {
  let secrets;
  secrets = await getSecretsInternal(primarySecretManager)
  return secrets
}

const getSecretsInternal = async client => {
  return new Promise((resolve, reject) => {
    client.getSecretValue({ SecretId: name }, (err, data) => {
      if (err) {
        switch (err.code) {
          case 'DecryptionFailureException':
            console.error(`Secrets Manager can't decrypt the protected secret text using the provided KMS key.`)
            break
          case 'InternalServiceErrorException':
            console.error(`An error occurred on the server side.`)
            break
          case 'InvalidParameterException':
            console.error(`You provided an invalid value for a parameter.`)
            break
          case 'InvalidRequestException':
            console.error(`You provided a parameter value that is not valid for the current state of the resource.`)
            break
          case 'ResourceNotFoundException':
            console.error(`We can't find the resource that you asked for.`)
            break
        }
        console.error(err)
        reject(err)
        return
      }

      // Decrypts secret using the associated KMS CMK.
      // Depending on whether the secret is a string or binary, one of these fields will be populated.
      let secrets;
      if ('SecretString' in data) {
        secrets = data.SecretString;
      } else {
        const buff = new Buffer(data.SecretBinary, 'base64');
        secrets = buff.toString('ascii');
      }

      resolve(JSON.parse(secrets))
    })
  })
}

module.exports = {
  getSecrets,
}