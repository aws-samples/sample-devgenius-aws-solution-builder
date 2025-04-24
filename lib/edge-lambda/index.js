/**
 * @fileoverview Lambda@Edge function that handles Cognito authentication for CloudFront distributions.
 * @module edge-lambda
 * @requires ./secretsManager
 * @requires cognito-at-edge
 */
const secretsManager = require('./secretsManager.js');
const { Authenticator } = require('cognito-at-edge');

/**
 * Lambda@Edge handler that authenticates requests using Amazon Cognito.
 * This function acts as a CloudFront viewer request handler to protect content
 * behind Cognito authentication.
 * 
 */
exports.handler = async (request) => {
  const secrets = await secretsManager.getSecrets();
  const authenticator = new Authenticator({
    region: secrets.Region, // user pool region
    userPoolId: secrets.UserPoolID, // user pool ID
    userPoolAppId: secrets.UserPoolAppId, // user pool app client ID
    userPoolDomain: secrets.DomainName, // user pool domain
  });
  return authenticator.handle(request);
};
